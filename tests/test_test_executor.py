from executor.test_executor import (
    is_url_in_scope,
    is_same_origin,
    validate_test_case,
    sanitize_response_body,
    redact_data
)


CONFIG = {
    "target_url": "http://localhost:8888/",
    "allowed_hosts": ["localhost"],
    "execution": {
        "enabled": True,
        "allow_mutation": False,
        "allowed_methods": [
            "GET",
            "HEAD",
            "OPTIONS"
        ]
    }
}


def make_test_case(
    method="GET",
    url="http://localhost:8888/api/v1/users/1",
    body=None
):
    return {
        "id": "TC001",
        "source_account": "test_user_a",
        "object_owner_account": "test_user_b",
        "method": method,
        "request": {
            "method": method,
            "url": url,
            "body": body
        }
    }


def test_url_inside_scope():
    assert is_url_in_scope(
        "http://localhost:8888/api/users",
        ["localhost"]
    )


def test_url_outside_scope():
    assert not is_url_in_scope(
        "http://example.com/api/users",
        ["localhost"]
    )


def test_reject_non_http_url():
    assert not is_url_in_scope(
        "file:///etc/passwd",
        ["localhost"]
    )


def test_same_origin():
    assert is_same_origin(
        "http://localhost:8888/api/users",
        "http://localhost:8888/"
    )


def test_reject_different_port():
    assert not is_same_origin(
        "http://localhost:8025/api/users",
        "http://localhost:8888/"
    )


def test_allow_safe_method():
    valid, reason = validate_test_case(
        make_test_case("GET"),
        CONFIG
    )

    assert valid
    assert reason is None


def test_reject_unsafe_method():
    valid, reason = validate_test_case(
        make_test_case("DELETE"),
        CONFIG
    )

    assert not valid
    assert "not allowed" in reason


def test_reject_request_outside_scope():
    valid, reason = validate_test_case(
        make_test_case(
            url="http://example.com/api/users"
        ),
        CONFIG
    )

    assert not valid
    assert "outside the allowed scope" in reason


def test_reject_different_origin():
    valid, reason = validate_test_case(
        make_test_case(
            url="http://localhost:8025/api/users"
        ),
        CONFIG
    )

    assert not valid
    assert "target origin" in reason


def test_reject_request_body_for_get():
    valid, reason = validate_test_case(
        make_test_case(
            "GET",
            body={"id": 2}
        ),
        CONFIG
    )

    assert not valid
    assert "Request body" in reason


def test_execution_disabled():
    config = {
        **CONFIG,
        "execution": {
            **CONFIG["execution"],
            "enabled": False
        }
    }

    valid, reason = validate_test_case(
        make_test_case(),
        config
    )

    assert not valid
    assert "disabled" in reason


def test_sanitize_json_response():
    body = sanitize_response_body(
        '{"id": 1, "token": "secret"}',
        "application/json"
    )

    assert body["id"] == 1
    assert body["token"] == "[REDACTED]"


def test_ignore_non_json_response():
    body = sanitize_response_body(
        "<html>Example</html>",
        "text/html"
    )

    assert body is None


def test_redact_nested_sensitive_data():
    data = {
        "id": 1,
        "user": {
            "email": "test@example.com",
            "name": "Test User"
        }
    }

    result = redact_data(data)

    assert result["id"] == 1
    assert result["user"]["email"] == "[REDACTED]"
    assert result["user"]["name"] == "Test User"
