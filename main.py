import asyncio
import json

from crawler.crawler import crawl


def load_config(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


async def main():
    config = load_config("config.json")

    print("Starting crawler...")
    print("Target URL:", config["target_url"])

    discovered = await crawl(config)

    print()
    print("Crawl finished.")
    print("Discovered pages:", len(discovered))

    for url in discovered:
        print("-", url)


if __name__ == "__main__":
    asyncio.run(main())