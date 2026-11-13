
import os
from urllib.parse import urlsplit

import httpx


def resolve_env(value):
    if not isinstance(value, str):
        return value

    if value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        env_value = os.getenv(env_name)

        if env_value is None:
            raise ValueError(
                f"Environment variable {env_name} is not set."
            )

        return env_value

    return value


async def create_authenticated_context(
    browser,
    target_url,
    auth_config,
    allowed_hosts,
    collector=None
):
    account_name = auth_config.get("active_account")
    accounts = auth_config.get("accounts", {})

    if account_name not in accounts:
        raise ValueError(
            f"Authentication account '{account_name}' is not configured."
        )

    account = accounts[account_name]

    email = resolve_env(account.get("email"))
    password = resolve_env(account.get("password"))

    if not email or not password:
        raise ValueError(
            f"Email or password is missing for '{account_name}'."
        )

    target = urlsplit(target_url)
    target_host = (target.hostname or "").lower()

    allowed_hosts = {
        host.strip().lower()
        for host in allowed_hosts
        if host and host.strip()
    }

    if target_host not in allowed_hosts:
        raise ValueError(
            "The target host is outside the configured allowed hosts."
        )

    target_origin = (
        target.scheme.lower(),
        target_host,
        target.port or (
            443 if target.scheme.lower() == "https" else 80
        )
    )

    base_url = f"{target.scheme}://{target.netloc}"
    login_url = f"{base_url}/identity/api/auth/login"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            login_url,
            json={
                "email": email,
                "password": password
            }
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Login failed for '{account_name}' "
            f"with HTTP {response.status_code}."
        )

    try:
        login_data = response.json()

    except ValueError as error:
        raise RuntimeError(
            f"Login response for '{account_name}' is not valid JSON."
        ) from error

    token = login_data.get("token")

    if not token:
        raise RuntimeError(
            f"Login response for '{account_name}' did not include a token."
        )

    print(f"Login successful for '{account_name}'.")
    print("JWT received successfully.")

    context = await browser.new_context()

    print("Authenticated browser context created.")

    async def add_auth_header(route):
        request_parts = urlsplit(route.request.url)

        request_origin = (
            request_parts.scheme.lower(),
            (request_parts.hostname or "").lower(),
            request_parts.port or (
                443 if request_parts.scheme.lower() == "https" else 80
            )
        )

        if request_origin != target_origin:
            await route.continue_()
            return

        headers = dict(route.request.headers)
        headers["authorization"] = f"Bearer {token}"

        await route.continue_(headers=headers)

        if collector is not None:
            collector.update_request_headers(
                route.request,
                headers
            )

    await context.route("**/*", add_auth_header)

    print("Authentication setup completed.")

    return context
