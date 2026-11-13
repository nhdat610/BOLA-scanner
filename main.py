import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

from crawler.crawler import crawl
from crawler.network_collector import NetworkCollector

from collector.normalizer import normalize_and_deduplicate
from collector.openapi_parser import (
    parse_openapi_file,
    fetch_openapi
)


def load_config(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(file_path, data):
    path = Path(file_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )


async def main():
    config = load_config("config.json")

    target_url = config["target_url"]

    allowed_domains = config["scope"]["allowed_domains"]

    allowed_hosts = config.get("allowed_hosts")

    if not allowed_hosts:
        allowed_hosts = allowed_domains

    print("Starting BOLA-scanner...")
    print("Target URL:", target_url)

    # 1. Create network collector.
    collector = NetworkCollector(allowed_hosts)

    # 2. Crawl the target and collect network traffic.
    discovered_urls = await crawl(
        config,
        collector=collector
    )

    # 3. Normalize and deduplicate requests.
    records = normalize_and_deduplicate(
        collector.records
    )

    network_output = {
        "total_requests": len(collector.records),
        "unique_requests": len(records),
        "requests": records
    }

    save_json(
        "data/network_traffic.json",
        network_output
    )

    # 4. Read OpenAPI/Swagger if configured.
    openapi_config = config.get("openapi", {})

    openapi_result = None

    if openapi_config.get("file"):
        print("Reading OpenAPI file...")

        openapi_result = parse_openapi_file(
            openapi_config["file"]
        )

    elif openapi_config.get("url"):
        print("Fetching OpenAPI specification...")

        openapi_result = await fetch_openapi(
            openapi_config["url"],
            allowed_hosts
        )

    if openapi_result is not None:
        save_json(
            "data/openapi_endpoints.json",
            openapi_result
        )

        print(
            "OpenAPI endpoints:",
            len(openapi_result["endpoints"])
        )

    else:
        print("No OpenAPI specification configured.")

    # 5. Print summary.
    print()
    print("Crawl finished.")
    print("Discovered pages:", len(discovered_urls))
    print("Collected requests:", len(collector.records))
    print("Unique requests:", len(records))
    print("Network data saved to data/network_traffic.json")

    if openapi_result is not None:
        print(
            "OpenAPI data saved to data/openapi_endpoints.json"
        )


if __name__ == "__main__":
    asyncio.run(main())