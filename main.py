import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

from crawler.crawler import crawl
from crawler.network_collector import NetworkCollector
from collector.normalizer import normalize_and_deduplicate


def load_config(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(file_path, data):
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


async def main():

    with open("config.json", "r", encoding="utf-8") as file:
        config = json.load(file)

    print("Starting crawler...")
    print("Target URL:", config["target_url"])

    allowed_hosts = config.get("allowed_hosts")

    if not allowed_hosts:
        allowed_hosts = [
            urlsplit(config["target_url"]).hostname
        ]

    collector = NetworkCollector(allowed_hosts)

    visited_urls = await crawl(config, collector=collector)

    records = normalize_and_deduplicate(
        collector.records
    )

    output = {
        "total_requests": len(collector.records),
        "unique_requests": len(records),
        "requests": records
    }

    save_json("data/network_traffic.json", output)

    print("Crawl finished.")
    print("Discovered pages:", len(visited_urls))
    print("Collected requests:", len(collector.records))
    print("Unique requests:", len(records))
    print("Network data saved to data/network_traffic.json")


if __name__ == "__main__":
    asyncio.run(main())