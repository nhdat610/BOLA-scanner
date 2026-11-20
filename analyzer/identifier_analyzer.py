import re
from urllib.parse import urlsplit
from uuid import UUID


IDENTIFIER_KEYS = {
    "id",
    "uuid",
    "identifier",
    "objectid",
    "object_id"
}


def is_identifier_key(key):
    """
    Check whether a field name may represent an object identifier.
    """
    if not isinstance(key, str):
        return False

    normalized = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])",
        "_",
        key
    ).lower()

    normalized = normalized.replace("-", "_")

    if normalized in IDENTIFIER_KEYS:
        return True

    if normalized.endswith("_id"):
        return True

    if normalized.endswith("_uuid"):
        return True

    if normalized.endswith("_identifier"):
        return True

    return False


def is_identifier_value(value):
    """
    Accept non-empty scalar identifier values.
    """
    if isinstance(value, bool) or value is None:
        return False

    if isinstance(value, (int, float)):
        return True

    if not isinstance(value, str):
        return False

    value = value.strip()

    if not value or value == "[REDACTED]":
        return False

    return True


def is_uuid(value):
    if not isinstance(value, str):
        return False

    try:
        UUID(value)
        return True
    except ValueError:
        return False


def is_path_identifier(value):
    """
    Detect numeric or UUID-like URL path segments.
    """
    if value.isdigit():
        return True

    return is_uuid(value)


def get_endpoint_template(url):
    """
    Replace numeric and UUID path segments with {id}.
    """
    parts = urlsplit(url)
    segments = parts.path.split("/")

    normalized_segments = []

    for segment in segments:
        if is_path_identifier(segment):
            normalized_segments.append("{id}")
        else:
            normalized_segments.append(segment)

    path = "/".join(normalized_segments)

    return path or "/"


def extract_body_identifiers(
    data,
    current_path="$",
    location="body"
):
    """
    Recursively extract identifiers from a JSON object or array.

    The location argument distinguishes request-body identifiers
    from response-body identifiers.
    """
    results = []

    if isinstance(data, dict):
        for key, value in data.items():
            field_path = f"{current_path}.{key}"

            if (
                is_identifier_key(key)
                and is_identifier_value(value)
            ):
                results.append({
                    "location": location,
                    "key": key,
                    "field_path": field_path,
                    "value": value
                })

            if isinstance(value, (dict, list)):
                results.extend(
                    extract_body_identifiers(
                        value,
                        field_path,
                        location
                    )
                )

    elif isinstance(data, list):
        for index, value in enumerate(data):
            results.extend(
                extract_body_identifiers(
                    value,
                    f"{current_path}[{index}]",
                    location
                )
            )

    return results


def analyze_request(record, account):
    """
    Analyze one HTTP record.

    Identifiers are extracted from:
    1. URL path
    2. Query parameters
    3. Request JSON body
    4. Response JSON body
    """
    url = record.get("url", "")
    parts = urlsplit(url)

    endpoint = get_endpoint_template(url)
    method = record.get("method", "").upper()

    results = []

    # 1. Extract identifiers from URL path.
    segments = parts.path.split("/")

    for index, segment in enumerate(segments):
        if not is_path_identifier(segment):
            continue

        results.append({
            "location": "path",
            "key": f"path_segment_{index}",
            "value": segment,
            "segment_index": index
        })

    # 2. Extract identifiers from query parameters.
    for parameter in record.get("query_params", []):
        key = parameter.get("name")
        value = parameter.get("value")

        if (
            is_identifier_key(key)
            and is_identifier_value(value)
        ):
            results.append({
                "location": "query",
                "key": key,
                "value": value
            })

    # 3. Extract identifiers from request JSON body.
    request_body = record.get("request_body")

    results.extend(
        extract_body_identifiers(
            request_body,
            location="body"
        )
    )

    # 4. Extract identifiers from response JSON body.
    response = record.get("response") or {}
    response_body = response.get("body")

    response_identifiers = extract_body_identifiers(
        response_body,
        location="response"
    )

    for item in response_identifiers:
        item["response_status"] = response.get("status")

    results.extend(response_identifiers)

    # Add request information to every identifier.
    for item in results:
        item["account"] = account
        item["method"] = method
        item["url"] = url
        item["endpoint"] = endpoint

    return results


def analyze_requests(records, account):
    """
    Analyze a collection of HTTP records and remove duplicates.
    """
    identifiers = []
    seen = set()

    for record in records:
        results = analyze_request(record, account)

        for item in results:
            key = (
                item["account"],
                item["method"],
                item["endpoint"],
                item["location"],
                item["key"],
                item.get("field_path"),
                str(item["value"])
            )

            if key in seen:
                continue

            seen.add(key)
            identifiers.append(item)

    return identifiers