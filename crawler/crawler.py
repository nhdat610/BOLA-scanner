from collections import deque
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Error as PlaywrightError

from auth.session import (
    create_authenticated_context,
    wait_for_manual_session,
)


def normalize_url(url):
    """
    Remove URL fragments and add a root path when missing.
    """
    parsed_url = urlparse(url)

    path = parsed_url.path or "/"

    return parsed_url._replace(
        path=path,
        fragment=""
    ).geturl()


def is_in_scope(url, allowed_hosts):
    """
    Check whether a URL belongs to one of the allowed hosts.
    """
    parsed_url = urlparse(url)

    if parsed_url.scheme not in {"http", "https"}:
        return False

    hostname = (parsed_url.hostname or "").lower()

    normalized_hosts = {
        host.lower()
        for host in allowed_hosts
        if isinstance(host, str) and host.strip()
    }

    return hostname in normalized_hosts


async def extract_navigation_urls(page, current_url, allowed_hosts):
    """
    Extract internal navigation URLs from the current page.
    """
    urls = set()

    try:
        links = await page.locator(
            'a[href], [role="link"][href]'
        ).evaluate_all(
            """
            elements => elements
                .map(element => element.getAttribute("href"))
                .filter(Boolean)
            """
        )

        for link in links:
            absolute_url = urljoin(current_url, link)
            normalized = normalize_url(absolute_url)

            if is_in_scope(normalized, allowed_hosts):
                urls.add(normalized)

    except PlaywrightError as error:
        print(f"Could not extract links: {error}")

    return urls


async def wait_for_page(page, config):
    """
    Wait for the page and its network activity to settle.
    """
    crawl_config = config.get("crawl", {})

    timeout_ms = crawl_config.get("network_wait_timeout_ms", 2000)

    try:
        await page.wait_for_load_state(
            "domcontentloaded",
            timeout=timeout_ms
        )
    except PlaywrightError:
        pass

    try:
        await page.wait_for_load_state(
            "networkidle",
            timeout=timeout_ms
        )
    except PlaywrightError:
        pass


async def wait_for_collector(collector):
    """
    Wait for pending network collection tasks, if supported
    by the current NetworkCollector implementation.
    """
    wait_method = getattr(collector, "wait_for_pending", None)

    if wait_method is not None:
        result = wait_method()

        if hasattr(result, "__await__"):
            await result


async def automatic_crawl(
    page,
    collector,
    target_url,
    start_url,
    config,
    allowed_hosts
):
    """
    Automatically crawl internal links after manual interaction.
    """
    crawl_config = config.get("crawl", {})

    max_pages = crawl_config.get("max_pages", 30)
    max_depth = crawl_config.get("max_depth", 2)
    timeout_ms = crawl_config.get("timeout_ms", 10000)

    queue = deque()
    visited = set()

    start_urls = [target_url]

    if start_url and start_url != target_url:
        start_urls.append(start_url)

    for url in start_urls:
        normalized = normalize_url(url)

        if is_in_scope(normalized, allowed_hosts):
            queue.append((normalized, 0))

    while queue and len(visited) < max_pages:
        current_url, depth = queue.popleft()

        if current_url in visited:
            continue

        if not is_in_scope(current_url, allowed_hosts):
            continue

        visited.add(current_url)

        print(f"Visiting: {current_url}")
        print(f"Depth: {depth}")

        try:
            response = await page.goto(
                current_url,
                wait_until="domcontentloaded",
                timeout=timeout_ms
            )

            await wait_for_page(page, config)

            await wait_for_collector(collector)

            if response is not None:
                print(f"Response status: {response.status}")

            final_url = normalize_url(page.url)

            if not is_in_scope(final_url, allowed_hosts):
                print("Navigation redirected outside the allowed scope.")
                continue

            if depth >= max_depth:
                continue

            discovered_urls = await extract_navigation_urls(
                page,
                final_url,
                allowed_hosts
            )

            for discovered_url in discovered_urls:
                if discovered_url not in visited:
                    queue.append((discovered_url, depth + 1))

        except PlaywrightError as error:
            print(f"Navigation failed: {error}")

        except Exception as error:
            print(f"Unexpected crawling error: {error}")

    await wait_for_collector(collector)

    return sorted(visited)


async def crawl(config, collector):
    """
    Run one complete scanning session for one account:

    1. Open a browser.
    2. Let the tester log in and interact manually.
    3. Continue with automatic internal-link crawling.
    4. Close the account's browser context.
    """
    target_url = config["target_url"]

    allowed_hosts = config.get("allowed_hosts")

    if not allowed_hosts:
        allowed_hosts = config.get("scope", {}).get(
            "allowed_domains", []
        )

    if not allowed_hosts:
        raise ValueError("No allowed hosts configured.")

    auth_config = config.get("auth", {})

    account_name = auth_config.get(
        "active_account",
        "anonymous"
    )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=False
        )

        context = await create_authenticated_context(
            browser,
            target_url,
            auth_config,
            allowed_hosts
        )

        page = await context.new_page()

        # Attach the collector before navigating to the target.
        collector.attach(page)

        print()
        print(f"Starting session for account: {account_name}")
        print(f"Target: {target_url}")

        try:
            await page.goto(
                target_url,
                wait_until="domcontentloaded",
                timeout=config.get("crawl", {}).get(
                    "timeout_ms",
                    10000
                )
            )

            await wait_for_page(page, config)

            # The tester logs in and explores the application manually.
            manual_start_url = await wait_for_manual_session(
                page,
                account_name
            )

            print()
            print("Starting automatic crawling...")

            visited_urls = await automatic_crawl(
                page=page,
                collector=collector,
                target_url=target_url,
                start_url=manual_start_url,
                config=config,
                allowed_hosts=allowed_hosts
            )

            await wait_for_collector(collector)

            print()
            print(f"Finished session for account: {account_name}")
            print(f"Discovered pages: {len(visited_urls)}")

            return visited_urls

        finally:
            await context.close()
            await browser.close()