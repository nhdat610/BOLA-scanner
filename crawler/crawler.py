from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse

from playwright.async_api import (
    async_playwright,
    Error as PlaywrightError
)

from auth.session import create_authenticated_context


def normalize_url(url):
    if not isinstance(url, str):
        return None

    parsed = urlparse(url)

    if parsed.scheme.lower() not in ("http", "https"):
        return None

    if not parsed.hostname:
        return None

    parsed = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=parsed.path or "/",
        fragment=""
    )

    return urlunparse(parsed)


def is_in_scope(url, allowed_domains):
    parsed = urlparse(url)

    if parsed.scheme.lower() not in ("http", "https"):
        return False

    if not parsed.hostname:
        return False

    return parsed.hostname.lower() in allowed_domains


async def crawl(config, collector=None):
    target_url = normalize_url(config["target_url"])

    allowed_domains = {
        domain.strip().lower()
        for domain in config["scope"]["allowed_domains"]
        if domain.strip()
    }

    max_pages = config["crawl"]["max_pages"]
    max_depth = config["crawl"]["max_depth"]

    timeout_ms = config["crawl"].get(
        "timeout_ms", 10000
    )

    network_wait_timeout_ms = config["crawl"].get(
        "network_wait_timeout_ms", 2000
    )

    if target_url is None:
        raise ValueError("Invalid target URL.")

    if not allowed_domains:
        raise ValueError("No allowed domain configured.")

    if not is_in_scope(target_url, allowed_domains):
        raise ValueError("Target URL is outside the allowed scope.")

    if (
        max_pages < 1
        or max_depth < 0
        or timeout_ms < 1
        or network_wait_timeout_ms < 0
    ):
        raise ValueError("Invalid crawl limits.")

    queue = deque([(target_url, 0)])

    queued_urls = {target_url}
    visited_urls = set()

    discovered = []
    discovered_set = set()

    pages_attempted = 0

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True
        )

        try:
            allowed_hosts = config.get("allowed_hosts")

            if not allowed_hosts:
                allowed_hosts = config["scope"]["allowed_domains"]

            context = await create_authenticated_context(
                browser,
                target_url,
                config.get("auth", {}),
                allowed_hosts,
                collector=collector
            )
            page = await context.new_page()

            if collector:
                collector.attach(page)

            while queue and pages_attempted < max_pages:
                url, depth = queue.popleft()

                if url in visited_urls:
                    continue

                visited_urls.add(url)
                pages_attempted += 1

                print(f"Visiting (depth {depth}): {url}")

                try:
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms
                    )

                except PlaywrightError as error:
                    print("Could not load:", url)
                    print("Reason:", error)

                    if collector:
                        await collector.wait_for_pending(
                            network_wait_timeout_ms
                        )

                    continue

                # Wait for network requests to finish.
                if collector:
                    await collector.wait_for_pending(
                        network_wait_timeout_ms
                    )

                current_url = normalize_url(page.url)

                if current_url is None:
                    continue

                if not is_in_scope(
                    current_url,
                    allowed_domains
                ):
                    print(
                        "Page is outside the allowed scope:",
                        page.url
                    )
                    continue

                visited_urls.add(current_url)

                if current_url not in discovered_set:
                    discovered.append(current_url)
                    discovered_set.add(current_url)

                if depth >= max_depth:
                    continue

                links = await page.locator("a").evaluate_all(
                    """
                    links => links.map(
                        link => link.getAttribute('href')
                    )
                    """
                )

                for link in links:
                    if not link:
                        continue

                    next_url = normalize_url(
                        urljoin(current_url, link)
                    )

                    if next_url is None:
                        continue

                    if not is_in_scope(
                        next_url,
                        allowed_domains
                    ):
                        continue

                    if (
                        next_url not in visited_urls
                        and next_url not in queued_urls
                    ):
                        queue.append((next_url, depth + 1))
                        queued_urls.add(next_url)

        finally:
            if collector:
                await collector.wait_for_pending(
                    network_wait_timeout_ms
                )

                await collector.wait_for_tasks()

            await browser.close()

    return discovered