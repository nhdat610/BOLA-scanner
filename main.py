
import asyncio
import json
from copy import deepcopy
from pathlib import Path

from crawler.crawler import crawl
from crawler.network_collector import NetworkCollector

from collector.normalizer import normalize_and_deduplicate

from collector.openapi_parser import (
    parse_openapi_file,
    fetch_openapi,
)

from analyzer.test_case_generator import generate_test_cases


CONFIG_PATH = Path("config.json")
DATA_DIR = Path("data")


def load_config():
    """
    Load the scanner configuration.
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {CONFIG_PATH}"
        )

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(file_path, data):
    """
    Save data to a JSON file.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )


def get_account_names(config):
    """
    Get the configured account names.

    If no accounts are configured, run one anonymous session.
    """
    accounts = config.get("auth", {}).get("accounts", {})

    if not accounts:
        return ["anonymous"]

    return list(accounts.keys())


async def run_account_session(config, account_name):
    """
    Run the crawler and network collector for one account.
    """
    account_config = deepcopy(config)

    account_config.setdefault("auth", {})
    account_config["auth"]["active_account"] = account_name

    allowed_hosts = account_config.get("allowed_hosts")

    if not allowed_hosts:
        allowed_hosts = account_config.get(
            "scope", {}
        ).get("allowed_domains", [])

    collector = NetworkCollector(allowed_hosts)

    print()
    print("=" * 60)
    print(f"Account: {account_name}")
    print("=" * 60)

    discovered_pages = await crawl(
        account_config,
        collector
    )

    # Normalize and remove duplicate requests.
    records = normalize_and_deduplicate(
        collector.records
    )

    # Associate each request with the account that generated it.
    for record in records:
        record["account"] = account_name

    print()
    print(f"Account: {account_name}")
    print(f"Discovered pages: {len(discovered_pages)}")
    print(f"Collected requests: {len(collector.records)}")
    print(f"Unique requests: {len(records)}")

    return records


async def main():
    config = load_config()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    target_url = config.get("target_url")

    if not target_url:
        raise ValueError("The target_url field is missing.")

    account_names = get_account_names(config)

    # Store requests separately for each account.
    account_records = {}

    # Store all requests together for the traffic report.
    all_network_records = []

    print("=" * 60)
    print("Starting BOLA-scanner")
    print("=" * 60)
    print(f"Target: {target_url}")
    print(f"Number of accounts: {len(account_names)}")

    # Run one isolated browser session for each account.
    for account_name in account_names:
        records = await run_account_session(
            config,
            account_name
        )

        account_records[account_name] = records
        all_network_records.extend(records)

    # Save collected network traffic.
    traffic_path = DATA_DIR / "network_traffic.json"

    save_json(
        traffic_path,
        {
            "total_requests": len(all_network_records),
            "accounts": account_names,
            "requests": all_network_records
        }
    )

    print()
    print(f"Network traffic saved to: {traffic_path}")

    # Analyze identifiers and generate cross-account test cases.
    analysis_result = generate_test_cases(
        account_records
    )

    analysis_path = (
        DATA_DIR / "identifiers_and_test_cases.json"
    )

    save_json(
        analysis_path,
        analysis_result
    )

    print()
    print(f"Analysis saved to: {analysis_path}")

    # Parse OpenAPI if a file or URL is configured.
    openapi_config = config.get("openapi", {})

    openapi_file = openapi_config.get("file")
    openapi_url = openapi_config.get("url")

    if openapi_file:
        print()
        print("Parsing OpenAPI specification from file...")

        openapi_result = parse_openapi_file(
            openapi_file
        )

        save_json(
            DATA_DIR / "openapi_spec.json",
            openapi_result
        )

    elif openapi_url:
        print()
        print("Fetching OpenAPI specification from URL...")

        openapi_result = await fetch_openapi(
            openapi_url,
            config.get("allowed_hosts")
            or config.get("scope", {}).get("allowed_domains", [])
        )

        save_json(
            DATA_DIR / "openapi_spec.json",
            openapi_result
        )

    else:
        print()
        print("No OpenAPI specification configured.")

    print()
    print("=" * 60)
    print("BOLA-scanner finished")
    print("=" * 60)
    print(f"Total collected requests: {len(all_network_records)}")
    print(f"Accounts processed: {len(account_names)}")
    print(f"Network traffic: {traffic_path}")
    print(f"Identifier analysis: {analysis_path}")
    print()
    print("Generated test cases have not been executed yet.")


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print()
        print("Scan interrupted by user.")

    except Exception as error:
        print()
        print(f"Scanner error: {error}")
