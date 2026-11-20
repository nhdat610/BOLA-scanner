from urllib.parse import urlparse


def validate_target(target_url, allowed_hosts):
    """
    Check whether the target URL belongs to the configured scope.
    """
    parsed_url = urlparse(target_url)

    if parsed_url.scheme not in {"http", "https"}:
        raise ValueError("Target URL must use HTTP or HTTPS.")

    target_host = (parsed_url.hostname or "").lower()

    normalized_hosts = {
        host.lower()
        for host in allowed_hosts
        if isinstance(host, str) and host.strip()
    }

    if not target_host or target_host not in normalized_hosts:
        raise ValueError(
            f"Target host '{target_host}' is not in the allowed hosts."
        )


async def create_authenticated_context(
    browser,
    target_url,
    auth_config=None,
    allowed_hosts=None
):
    """
    Create an isolated browser context for one test account.

    Authentication is performed manually by the tester in the browser.
    The function name is retained to avoid changing existing imports.
    """
    allowed_hosts = allowed_hosts or []

    validate_target(target_url, allowed_hosts)

    context = await browser.new_context()

    return context


async def wait_for_manual_session(page, account_name):
    """
    Wait until the tester finishes logging in and manually exploring
    the target application.

    The browser remains open while the tester interacts with the website.
    """
    print()
    print("=" * 60)
    print(f"Manual session: {account_name}")
    print("=" * 60)
    print("A browser window has been opened.")
    print("Please log in and interact with the application.")
    print("The scanner is recording in-scope network requests.")
    print()
    print("When you finish, return to this terminal and press Enter.")
    print("=" * 60)

    await __import__("asyncio").to_thread(
        input,
        "Press Enter to continue with automatic crawling..."
    )

    current_url = page.url

    print()
    print(f"Manual interaction completed for '{account_name}'.")
    print(f"Current browser URL: {current_url}")

    return current_url