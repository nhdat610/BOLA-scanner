from analyzer.test_case_generator import (
    generate_test_cases,
    replace_identifier
)


def make_record(url, method="GET", body=None, query=None):
    from urllib.parse import urlsplit, parse_qsl

    if query is None:
        query = [
            {"name": key, "value": value}
            for key, value in parse_qsl(
                urlsplit(url).query
            )
        ]

    return {
        "method": method,
        "url": url,
        "path": urlsplit(url).path,
        "query_params": query,
        "request_body": body
    }


def test_replace_path_identifier():
    record = make_record(
        "http://localhost:8888/api/orders/101"
    )

    identifier = {
        "location": "path",
        "segment_index": 3
    }

    result = replace_identifier(
        record,
        identifier,
        "202"
    )

    assert result["url"].endswith("/202")


def test_replace_query_identifier():
    record = make_record(
        "http://localhost:8888/api/orders?user_id=101"
    )

    identifier = {
        "location": "query",
        "key": "user_id"
    }

    result = replace_identifier(
        record,
        identifier,
        "202"
    )

    assert "user_id=202" in result["url"]


def test_replace_body_identifier():
    record = make_record(
        "http://localhost:8888/api/orders",
        method="POST",
        body={"user_id": 101}
    )

    identifier = {
        "location": "body",
        "field_path": "$.user_id"
    }

    result = replace_identifier(
        record,
        identifier,
        202
    )

    assert result["body"]["user_id"] == 202

    # Original request must remain unchanged.
    assert record["request_body"]["user_id"] == 101


def test_generate_cross_account_test_cases():
    account_records = {
        "account_a": [
            make_record(
                "http://localhost:8888/api/orders/101"
            )
        ],
        "account_b": [
            make_record(
                "http://localhost:8888/api/orders/202"
            )
        ]
    }

    result = generate_test_cases(account_records)

    assert result["total_identifiers"] == 2
    assert result["total_test_cases"] == 2

    cases = result["test_cases"]

    assert cases[0]["source_account"] == "account_a"
    assert cases[0]["object_owner_account"] == "account_b"

    assert cases[0]["request"]["url"].endswith("/202")

    assert cases[1]["source_account"] == "account_b"
    assert cases[1]["object_owner_account"] == "account_a"

    assert cases[1]["request"]["url"].endswith("/101")

    assert all(
        case["executed"] is False
        for case in cases
    )
