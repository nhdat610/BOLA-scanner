import re

from copy import deepcopy
from urllib.parse import (
    urlsplit,
    urlunsplit,
    parse_qsl,
    urlencode
)

from analyzer.identifier_analyzer import (
    analyze_request,
    get_endpoint_template
)


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

REQUEST_IDENTIFIER_LOCATIONS = {
    "path",
    "query",
    "body"
}


def replace_path_identifier(url, index, new_value):
    parts = urlsplit(url)
    segments = parts.path.split("/")

    if index >= len(segments):
        return None

    segments[index] = str(new_value)

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        "/".join(segments),
        parts.query,
        ""
    ))


def replace_query_identifier(url, key, new_value):
    parts = urlsplit(url)

    parameters = parse_qsl(
        parts.query,
        keep_blank_values=True
    )

    replaced = False
    result = []

    for name, value in parameters:
        if name == key and not replaced:
            result.append((name, str(new_value)))
            replaced = True
        else:
            result.append((name, value))

    if not replaced:
        return None

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(result),
        ""
    ))


def replace_body_identifier(body, field_path, new_value):
    result = deepcopy(body)

    if not isinstance(result, (dict, list)):
        return None

    tokens = re.findall(
        r"[^.\[\]]+|\[\d+\]",
        field_path[2:]
    )

    if not tokens:
        return None

    current = result

    # Navigate to the parent of the target field.
    for token in tokens[:-1]:

        if token.startswith("["):
            index = int(token[1:-1])

            if not isinstance(current, list):
                return None

            if index >= len(current):
                return None

            current = current[index]

        else:
            if not isinstance(current, dict):
                return None

            if token not in current:
                return None

            current = current[token]

    # Replace the target field.
    final = tokens[-1]

    if final.startswith("["):
        index = int(final[1:-1])

        if not isinstance(current, list):
            return None

        if index >= len(current):
            return None

        current[index] = new_value

    else:
        if not isinstance(current, dict):
            return None

        if final not in current:
            return None

        current[final] = new_value

    return result


def replace_identifier(record, identifier, new_value):
    request = {
        "method": record["method"],
        "url": record["url"],
        "body": deepcopy(record.get("request_body"))
    }

    location = identifier["location"]

    if location == "path":
        request["url"] = replace_path_identifier(
            request["url"],
            identifier["segment_index"],
            new_value
        )

    elif location == "query":
        request["url"] = replace_query_identifier(
            request["url"],
            identifier["key"],
            new_value
        )

    elif location == "body":
        request["body"] = replace_body_identifier(
            request["body"],
            identifier["field_path"],
            new_value
        )

    else:
        return None

    if request["url"] is None:
        return None

    if location == "body" and request["body"] is None:
        return None

    return request


def generate_test_cases(account_records):
    """
    Generate cross-account test cases from request identifiers.

    Response identifiers are collected as reference data but are
    not directly used to modify requests.
    """
    identifiers = {}

    # 1. Analyze requests separately for each account.
    for account, records in account_records.items():
        identifiers[account] = []

        for record in records:
            found = analyze_request(record, account)

            for item in found:
                item["record"] = record
                identifiers[account].append(item)

    # 2. Count request and response identifiers.
    total_request_identifiers = 0
    total_response_identifiers = 0

    for items in identifiers.values():
        for item in items:
            if item["location"] == "response":
                total_response_identifiers += 1
            else:
                total_request_identifiers += 1

    # 3. Generate cross-account test cases.
    test_cases = []
    seen = set()
    counter = 1

    for account, records in account_records.items():

        for record in records:
            method = record.get("method", "").upper()
            endpoint = get_endpoint_template(record["url"])

            # Only identifiers found in the request can be replaced.
            base_items = [
                item for item in identifiers[account]
                if (
                    item["method"] == method
                    and item["endpoint"] == endpoint
                    and item["record"] is record
                    and item["location"] in REQUEST_IDENTIFIER_LOCATIONS
                )
            ]

            for base in base_items:

                for owner, owner_items in identifiers.items():

                    if owner == account:
                        continue

                    candidates = [
                        item for item in owner_items
                        if (
                            item["method"] == method
                            and item["endpoint"] == endpoint
                            and item["location"] == base["location"]
                            and item["key"] == base["key"]
                            and item.get("field_path") == base.get("field_path")
                        )
                    ]

                    for candidate in candidates:

                        if str(base["value"]) == str(candidate["value"]):
                            continue

                        unique_key = (
                            account,
                            owner,
                            method,
                            endpoint,
                            base["location"],
                            base["key"],
                            base.get("field_path"),
                            str(base["value"]),
                            str(candidate["value"])
                        )

                        if unique_key in seen:
                            continue

                        seen.add(unique_key)

                        modified = replace_identifier(
                            record,
                            base,
                            candidate["value"]
                        )

                        if modified is None:
                            continue

                        test_cases.append({
                            "id": f"TC{counter:03d}",
                            "source_account": account,
                            "object_owner_account": owner,
                            "method": method,
                            "endpoint": endpoint,
                            "location": base["location"],
                            "identifier_key": base["key"],
                            "field_path": base.get("field_path"),
                            "original_value": base["value"],
                            "replacement_value": candidate["value"],
                            "request": modified,
                            "safe_method": method in SAFE_METHODS,
                            "status": "generated",
                            "executed": False
                        })

                        counter += 1

    # 4. Prepare output.
    return {
        "total_identifiers": (
            total_request_identifiers
            + total_response_identifiers
        ),
        "total_request_identifiers": total_request_identifiers,
        "total_response_identifiers": total_response_identifiers,
        "total_test_cases": len(test_cases),

        "identifiers": {
            account: [
                {
                    key: value
                    for key, value in item.items()
                    if key != "record"
                }
                for item in items
            ]
            for account, items in identifiers.items()
        },

        "test_cases": test_cases
    }