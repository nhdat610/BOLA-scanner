import asyncio
import json
import time

from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError

from auth.session import (
    create_authenticated_context,
    wait_for_manual_session
)


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_allowed_hosts(config):
    """
    Get the configured allowed hosts.
    """
    return (
        config.get("allowed_hosts")
        or config.get("scope", {}).get(
            "allowed_domains", []
        )
    )


def is_url_in_scope(url, allowed_hosts):
    """
    Check whether a URL belongs to the allowed hosts.
    """
    try:
        parts = urlsplit(url)

        if parts.scheme.lower() not in {"http", "https"}:
            return False

        hostname = (parts.hostname or "").lower()

        normalized_hosts = {
            host.lower()
            for host in allowed_hosts
            if isinstance(host, str) and host.strip()
        }

        return hostname in normalized_hosts

    except (ValueError, TypeError):
        return False


def is_same_origin(url, target_url):
    """
    Check whether two URLs have the same scheme, hostname and port.
    """
    try:
        first = urlsplit(url)
        second = urlsplit(target_url)

        return (
            first.scheme.lower() == second.scheme.lower()
            and (first.hostname or "").lower()
                == (second.hostname or "").lower()
            and first.port == second.port
        )

    except ValueError:
        return False


def validate_test_case(test_case, config):
    """
    Validate a test case before execution.
    """
    execution_config = config.get("execution", {})

    if not execution_config.get("enabled", True):
        return False, "Execution is disabled."

    if not isinstance(test_case, dict):
        return False, "Invalid test case."

    request = test_case.get("request")

    if not isinstance(request, dict):
        return False, "Invalid request data."

    method = str(request.get("method", "")).upper()
    url = request.get("url")

    if not method or not isinstance(url, str):
        return False, "Missing request method or URL."

    if method not in {
        "GET", "HEAD", "OPTIONS",
        "POST", "PUT", "PATCH", "DELETE"
    }:
        return False, "Unsupported HTTP method."

    allowed_hosts = get_allowed_hosts(config)

    if not is_url_in_scope(url, allowed_hosts):
        return False, "Request URL is outside the allowed scope."

    if not is_same_origin(url, config["target_url"]):
        return False, "Request URL is outside the target origin."

    allowed_methods = {
        item.upper()
        for item in execution_config.get(
            "allowed_methods",
            list(SAFE_METHODS)
        )
    }

    if method not in allowed_methods:
        return False, f"HTTP method {method} is not allowed."

    if method not in SAFE_METHODS:
        if not execution_config.get("allow_mutation", False):
            return False, "Potentially modifying request blocked."

    if method in {"GET", "HEAD"} and request.get("body") is not None:
        return False, "Request body is not allowed for this method."

    return True, None


def redact_data(data):
    """
    Recursively redact sensitive fields in JSON data.
    """
    sensitive_keys = {
        "authorization",
        "cookie",
        "set-cookie",
        "token",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "api_key",
        "session",
        "email",
        "phone",
        "phonenumber"
    }

    if isinstance(data, dict):
        result = {}

        for key, value in data.items():
            normalized = str(key).lower().replace("-", "_")

            if (
                normalized in sensitive_keys
                or any(
                    item in normalized
                    for item in sensitive_keys
                )
            ):
                result[key] = "[REDACTED]"
            else:
                result[key] = redact_data(value)

        return result

    if isinstance(data, list):
        return [
            redact_data(item)
            for item in data
        ]

    return data


def sanitize_response_body(text, content_type):
    """
    Parse and redact a JSON response body.
    """
    if not text:
        return None

    if "json" not in content_type.lower():
        return None

    try:
        data = json.loads(text)
        return redact_data(data)

    except (json.JSONDecodeError, TypeError):
        return None


async def send_browser_request(
    page,
    test_case,
    timeout_ms,
    max_response_body
):
    """
    Send a request using the authenticated browser session.

    Only same-origin requests are supported.
    Redirects are rejected to prevent following an
    unexpected destination.
    """
    request = test_case["request"]

    payload = {
        "method": request["method"].upper(),
        "url": request["url"],
        "body": request.get("body"),
        "timeout": timeout_ms,
        "max_response_body": max_response_body
    }

    result = await page.evaluate(
        """
        async (request) => {
            const controller = new AbortController();

            const timer = setTimeout(
                () => controller.abort(),
                request.timeout
            );

            try {
                const options = {
                    method: request.method,
                    credentials: "include",
                    redirect: "error",
                    signal: controller.signal,
                    headers: {}
                };

                if (
                    request.body !== null &&
                    request.body !== undefined
                ) {
                    options.headers["Content-Type"] =
                        "application/json";

                    options.body = JSON.stringify(
                        request.body
                    );
                }

                const response = await fetch(
                    request.url,
                    options
                );

                const headers = Object.fromEntries(
                    response.headers.entries()
                );

                const contentType =
                    headers["content-type"] || "";

                let body = "";
                let bodyTruncated = false;

                if (
                    response.body &&
                    contentType.toLowerCase().includes("json")
                ) {
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();

                    let totalBytes = 0;
                    const chunks = [];

                    while (true) {
                        const { done, value } =
                            await reader.read();

                        if (done) {
                            break;
                        }

                        totalBytes += value.length;

                        if (
                            totalBytes >
                            request.max_response_body
                        ) {
                            bodyTruncated = true;
                            await reader.cancel();
                            break;
                        }

                        chunks.push(
                            decoder.decode(value, {
                                stream: true
                            })
                        );
                    }

                    if (!bodyTruncated) {
                        chunks.push(decoder.decode());
                        body = chunks.join("");
                    }
                }

                return {
                    status: response.status,
                    url: response.url,
                    headers: headers,
                    body: body,
                    body_truncated: bodyTruncated
                };

            } catch (error) {
                return {
                    error: error.name === "AbortError"
                        ? "Request timed out."
                        : error.message
                };

            } finally {
                clearTimeout(timer);
            }
        }
        """,
        payload
    )

    if result.get("error"):
        return {
            "status": None,
            "final_url": None,
            "headers": {},
            "body": None,
            "body_truncated": False,
            "error": result["error"]
        }

    final_url = result.get("url")

    if not is_same_origin(
        final_url,
        page.url
    ):
        return {
            "status": result.get("status"),
            "final_url": None,
            "headers": {},
            "body": None,
            "body_truncated": False,
            "error": "Response URL is outside the current page origin."
        }

    headers = redact_data(
        result.get("headers", {})
    )

    content_type = result.get(
        "headers", {}
    ).get("content-type", "")

    body = sanitize_response_body(
        result.get("body", ""),
        content_type
    )

    return {
        "status": result["status"],
        "final_url": final_url,
        "headers": headers,
        "body": body,
        "body_truncated": result.get(
            "body_truncated", False
        ),
        "error": None
    }


async def execute_account_test_cases(
    browser,
    config,
    account_name,
    test_cases
):
    """
    Execute test cases using one account's browser session.
    """
    target_url = config["target_url"]

    auth_config = config.get("auth", {})
    allowed_hosts = get_allowed_hosts(config)

    execution_config = config.get("execution", {})

    timeout_ms = max(
        1,
        execution_config.get("timeout_ms", 10000)
    )

    delay_ms = max(
        0,
        execution_config.get("delay_ms", 500)
    )

    max_response_body = max(
        0,
        execution_config.get("max_response_body", 100000)
    )

    context = await create_authenticated_context(
        browser,
        target_url,
        auth_config,
        allowed_hosts
    )

    results = []

    try:
        page = await context.new_page()

        await page.goto(
            target_url,
            wait_until="domcontentloaded",
            timeout=timeout_ms
        )

        await wait_for_manual_session(
            page,
            account_name
        )

        # The manually authenticated page must remain
        # on the target origin.
        if not is_same_origin(page.url, target_url):
            raise ValueError(
                "Browser page is outside the target origin."
            )

        print()
        print(f"Executing test cases for: {account_name}")

        for index, test_case in enumerate(test_cases):

            valid, reason = validate_test_case(
                test_case,
                config
            )

            result = {
                "test_case_id": test_case.get("id"),
                "source_account": account_name,
                "object_owner_account": test_case.get(
                    "object_owner_account"
                ),
                "method": test_case.get("method"),
                "endpoint": test_case.get("endpoint"),
                "location": test_case.get("location"),
                "executed": False,
                "status": "skipped",
                "reason": reason,
                "execution_time": None,
                "response": None
            }

            if not valid:
                print(
                    f"Skipped {test_case.get('id')}: {reason}"
                )

                results.append(result)
                continue

            print(
                f"Executing {test_case.get('id')}: "
                f"{test_case.get('method')} "
                f"{test_case.get('endpoint')}"
            )

            started_at = time.perf_counter()

            try:
                response = await send_browser_request(
                    page,
                    test_case,
                    timeout_ms,
                    max_response_body
                )

            except PlaywrightError as error:
                response = {
                    "status": None,
                    "final_url": None,
                    "headers": {},
                    "body": None,
                    "body_truncated": False,
                    "error": str(error)
                }

            duration_ms = (
                time.perf_counter() - started_at
            ) * 1000

            result["executed"] = True

            result["execution_time"] = round(
                duration_ms, 2
            )

            result["response"] = response

            if response["error"]:
                result["status"] = "error"
            else:
                result["status"] = "completed"

            results.append(result)

            print(
                f"Result: {result['status']}"
            )

            if index < len(test_cases) - 1:
                await asyncio.sleep(
                    delay_ms / 1000
                )

        return results

    finally:
        await context.close()


async def execute_test_cases(test_cases, config):
    """
    Execute generated test cases using the corresponding
    source account session.
    """
    execution_config = config.get("execution", {})

    if not execution_config.get("enabled", True):
        print("Test case execution is disabled.")
        return []

    max_requests = max(
        0,
        execution_config.get("max_requests", 50)
    )

    if not isinstance(test_cases, list):
        raise ValueError("Invalid test case collection.")

    accounts = config.get("auth", {}).get(
        "accounts", {}
    )

    account_names = (
        list(accounts.keys())
        if accounts
        else ["anonymous"]
    )

    # Apply the global limit before grouping by account.
    selected_cases = test_cases[:max_requests]

    results = []

    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=False
        )

        try:
            for account_name in account_names:

                account_cases = [
                    case for case in selected_cases
                    if case.get("source_account")
                    == account_name
                ]

                if not account_cases:
                    continue

                print()
                print("=" * 60)
                print(f"Execution account: {account_name}")
                print("=" * 60)

                account_results = (
                    await execute_account_test_cases(
                        browser,
                        config,
                        account_name,
                        account_cases
                    )
                )

                results.extend(account_results)

        finally:
            await browser.close()

    return results
