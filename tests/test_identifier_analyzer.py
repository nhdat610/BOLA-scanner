from analyzer.identifier_analyzer import (
    is_identifier_key,
    get_endpoint_template,
    analyze_request
)


def test_identifier_key():
    assert is_identifier_key("id")
    assert is_identifier_key("user_id")
    assert is_identifier_key("productId")
    assert is_identifier_key("uuid")

    assert not is_identifier_key("username")


def test_endpoint_template():
    url = "https://example.com/api/orders/101"

    result = get_endpoint_template(url)

    assert result == "/api/orders/{id}"


def test_extract_path_identifier():
    record = {
        "method": "GET",
        "url": "https://example.com/api/orders/101",
        "query_params": [],
        "request_body": None
    }

    result = analyze_request(record, "account_a")

    assert len(result) == 1
    assert result[0]["location"] == "path"
    assert result[0]["value"] == "101"


def test_extract_query_identifier():
    record = {
        "method": "GET",
        "url": "https://example.com/api/orders?user_id=101",
        "query_params": [
            {
                "name": "user_id",
                "value": "101"
            }
        ],
        "request_body": None
    }

    result = analyze_request(record, "account_a")

    assert len(result) == 1
    assert result[0]["location"] == "query"


def test_extract_json_body_identifier():
    record = {
        "method": "POST",
        "url": "https://example.com/api/orders",
        "query_params": [],
        "request_body": {
            "order_id": 101,
            "user": {
                "user_id": 202
            }
        }
    }

    result = analyze_request(record, "account_a")

    assert len(result) == 2

    values = {
        item["value"] for item in result
    }

    assert values == {101, 202}


def test_ignore_redacted_identifier():
    record = {
        "method": "GET",
        "url": "https://example.com/api/orders?user_id=%5BREDACTED%5D",
        "query_params": [
            {
                "name": "user_id",
                "value": "[REDACTED]"
            }
        ],
        "request_body": None
    }

    result = analyze_request(record, "account_a")

    assert len(result) == 0
