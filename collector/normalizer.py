import json
from urllib.parse import urlsplit, urlunsplit, parse_qsl


def normalize_record(record):
    result = dict(record)

    parts = urlsplit(record["url"])

    normalized_url = urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path or "/",
        parts.query,
        ""
    ))

    result["url"] = normalized_url
    result["path"] = parts.path or "/"

    result["query_params"] = [
        {
            "name": key,
            "value": value
        }
        for key, value in parse_qsl(
            parts.query,
            keep_blank_values=True
        )
    ]

    return result


def normalize_and_deduplicate(records):
    unique_records = {}

    for record in records:
        item = normalize_record(record)

        body_key = json.dumps(
            item["request_body"],
            sort_keys=True,
            ensure_ascii=False
        )

        key = (
            item["method"],
            item["url"],
            body_key
        )

        if key not in unique_records:
            item["occurrences"] = 1
            unique_records[key] = item

        else:
            existing = unique_records[key]
            existing["occurrences"] += 1

            if (
                existing["response"] is None
                and item["response"] is not None
            ):
                existing["response"] = item["response"]

    return list(unique_records.values())