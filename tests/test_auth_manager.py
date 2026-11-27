from auth.auth_manager import AuthenticationManager, capture_authorization_header


def test_cookie_header_is_built_for_account_session():
    manager = AuthenticationManager({"accounts": {"a": {}}})
    headers = manager.build_headers(
        "a", "http://localhost:8888/",
        [{"name": "JSESSIONID", "value": "abc", "domain": "localhost"}],
        {}
    )
    assert headers["Cookie"] == "JSESSIONID=abc"


def test_captured_bearer_is_reused():
    manager = AuthenticationManager({"accounts": {"a": {}}})
    headers = manager.build_headers(
        "a", "http://localhost:8888/", [],
        {"authorization": "Bearer test-token"}
    )
    assert headers["Authorization"] == "Bearer test-token"


def test_custom_headers_override_captured_values():
    manager = AuthenticationManager({
        "accounts": {"a": {"custom_headers": {"X-Test": "yes"}}}
    })
    headers = manager.build_headers("a", "http://localhost:8888/", [], {})
    assert headers["X-Test"] == "yes"


def test_authorization_capture_rejects_other_origin():
    class Request:
        url = "http://localhost:8025/api"
        headers = {"authorization": "Bearer secret"}

    assert capture_authorization_header(
        Request(), "http://localhost:8888/"
    ) is None
