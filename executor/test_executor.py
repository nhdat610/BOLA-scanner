import asyncio
import json
import time
from urllib.parse import urlsplit

import httpx
from playwright.async_api import async_playwright, Error as PlaywrightError

from auth.session import create_authenticated_context, wait_for_manual_session
from auth.auth_manager import AuthenticationManager, capture_authorization_header


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SENSITIVE_KEYS = {
    "authorization", "cookie", "set-cookie", "token", "access_token",
    "refresh_token", "password", "secret", "api_key", "session", "email", "phone"
}


def get_allowed_hosts(config):
    hosts = config.get("allowed_hosts") or config.get("scope", {}).get(
        "allowed_domains", []
    )
    return {str(host).lower() for host in hosts}


def _origin(url):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return parts.scheme.lower(), parts.hostname.lower(), port


def is_url_in_scope(url, allowed_hosts):
    try:
        parts = urlsplit(url)
        return (
            parts.scheme in {"http", "https"}
            and parts.hostname is not None
            and parts.username is None
            and parts.password is None
            and parts.hostname.lower() in {
                str(host).lower() for host in allowed_hosts
            }
        )
    except ValueError:
        return False


def is_same_origin(url, target_url):
    return _origin(url) is not None and _origin(url) == _origin(target_url)


def validate_test_case(test_case, config):
    execution = config.get("execution", {})
    if not execution.get("enabled", True):
        return False, "Test case execution is disabled."

    request = test_case.get("request")
    if not isinstance(request, dict):
        return False, "Missing request object."

    method = str(request.get("method") or test_case.get("method") or "").upper()
    url = request.get("url")
    if not method or not isinstance(url, str):
        return False, "Invalid request method or URL."

    if not is_url_in_scope(url, get_allowed_hosts(config)):
        return False, "Request URL is outside the allowed scope."

    if not is_same_origin(url, config["target_url"]):
        return False, "Request URL is outside the target origin."

    allowed_methods = {
        str(item).upper()
        for item in execution.get("allowed_methods", list(SAFE_METHODS))
    }
    if method not in allowed_methods:
        return False, f"HTTP method {method} is not allowed."

    if method not in SAFE_METHODS and not execution.get("allow_mutation", False):
        return False, "Potentially modifying request blocked."

    if method in {"GET", "HEAD"} and request.get("body") is not None:
        return False, f"Request body is not allowed for {method}."

    return True, None


def redact_data(data):
    if isinstance(data, dict):
        return {
            key: "[REDACTED]" if any(
                token in str(key).lower().replace("-", "_")
                for token in SENSITIVE_KEYS
            ) else redact_data(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [redact_data(value) for value in data]
    return data


def sanitize_response_body(raw, content_type):
    if not raw or "json" not in (content_type or "").lower():
        return None
    try:
        return redact_data(json.loads(raw))
    except (ValueError, TypeError):
        return None


def sanitize_headers(headers):
    return {
        key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else value
        for key, value in headers.items()
    }


async def _execute_one(client, test_case, timeout_ms, max_body):
    request = test_case["request"]
    method = str(request.get("method") or test_case.get("method")).upper()
    started = time.perf_counter()
    try:
        async with client.stream(
            method,
            request["url"],
            json=request.get("body") if request.get("body") is not None else None,
            timeout=timeout_ms / 1000,
            follow_redirects=False
        ) as response:
            chunks = []
            size = 0
            truncated = False
            async for chunk in response.aiter_bytes():
                remaining = max_body - size
                if remaining <= 0:
                    truncated = True
                    break
                chunks.append(chunk[:remaining])
                size += min(len(chunk), remaining)
                if len(chunk) > remaining:
                    truncated = True
                    break
            raw = b"".join(chunks)
            content_type = response.headers.get("content-type", "")
            body = None if truncated else sanitize_response_body(
                raw.decode("utf-8", errors="replace"), content_type
            )
            result = {
                "status": response.status_code,
                "final_url": str(response.url),
                "headers": sanitize_headers(dict(response.headers)),
                "body": body,
                "body_truncated": truncated,
                "error": None
            }
    except (httpx.HTTPError, ValueError) as error:
        result = {
            "status": None, "final_url": None, "headers": {},
            "body": None, "body_truncated": False,
            "error": f"{type(error).__name__}: {error}"
        }
    return result, round((time.perf_counter() - started) * 1000, 2)


async def execute_account_test_cases(browser, config, account_name, test_cases):
    target_url = config["target_url"]
    allowed_hosts = get_allowed_hosts(config)
    execution = config.get("execution", {})
    timeout_ms = max(1, int(execution.get("timeout_ms", 10000)))
    delay_ms = max(0, int(execution.get("delay_ms", 500)))
    max_body = max(0, int(execution.get("max_response_body", 100000)))

    context = await create_authenticated_context(
        browser, target_url, config.get("auth", {}), allowed_hosts
    )
    results = []
    captured = {}

    def observe_request(request):
        value = capture_authorization_header(request, target_url)
        if value:
            captured["authorization"] = value

    try:
        page = await context.new_page()
        page.on("request", observe_request)
        await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
        await wait_for_manual_session(page, account_name)

        if not is_same_origin(page.url, target_url):
            raise ValueError("Authenticated browser page is outside target origin.")

        cookies = await context.cookies([target_url])
        auth_manager = AuthenticationManager(config.get("auth", {}))
        headers = auth_manager.build_headers(
            account_name, target_url, cookies, captured
        )

        # Do not forward browser-only or hop-by-hop headers.
        headers.setdefault("Accept", "application/json, */*")
        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout_ms / 1000,
            follow_redirects=False
        ) as client:
            for index, test_case in enumerate(test_cases):
                valid, reason = validate_test_case(test_case, config)
                item = {
                    "test_case_id": test_case.get("id"),
                    "source_account": account_name,
                    "object_owner_account": test_case.get("object_owner_account"),
                    "method": test_case.get("method"),
                    "endpoint": test_case.get("endpoint"),
                    "location": test_case.get("location"),
                    "executed": False,
                    "status": "skipped",
                    "reason": reason,
                    "execution_time": None,
                    "response": None
                }
                if valid:
                    response, elapsed = await _execute_one(
                        client, test_case, timeout_ms, max_body
                    )
                    item["executed"] = True
                    item["execution_time"] = elapsed
                    item["response"] = response
                    item["status"] = (
                        "completed" if response["error"] is None else "error"
                    )
                results.append(item)
                if index < len(test_cases) - 1 and delay_ms:
                    await asyncio.sleep(delay_ms / 1000)
        return results
    finally:
        await context.close()


async def execute_test_cases(test_cases, config):
    execution = config.get("execution", {})
    if not execution.get("enabled", True):
        print("Test case execution is disabled.")
        return []
    if not isinstance(test_cases, list):
        raise ValueError("Test cases must be a list.")

    max_requests = max(0, int(execution.get("max_requests", 50)))
    accounts = config.get("auth", {}).get("accounts", {})
    account_names = list(accounts) if accounts else ["anonymous"]
    selected = test_cases[:max_requests]
    results = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        try:
            for account_name in account_names:
                account_cases = [
                    case for case in selected
                    if case.get("source_account") == account_name
                ]
                if account_cases:
                    print(f"Starting execution session: {account_name}")
                    results.extend(await execute_account_test_cases(
                        browser, config, account_name, account_cases
                    ))
        finally:
            await browser.close()
    return results
