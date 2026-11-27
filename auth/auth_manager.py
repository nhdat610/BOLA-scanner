from urllib.parse import urlsplit

from auth.providers.cookie import cookie_header
from auth.providers.bearer import bearer_header
from auth.providers.custom_headers import resolve_header_values


SENSITIVE_HEADER_NAMES = {
    "authorization", "cookie", "set-cookie", "x-api-key"
}


def _same_origin(left, right):
    a, b = urlsplit(left), urlsplit(right)
    def port(p):
        return p.port or (443 if p.scheme == "https" else 80)
    return (
        a.scheme.lower() == b.scheme.lower()
        and (a.hostname or "").lower() == (b.hostname or "").lower()
        and port(a) == port(b)
    )


class AuthenticationManager:
    """Build per-account HTTP headers from an isolated browser session."""

    def __init__(self, auth_config=None):
        self.auth_config = auth_config or {}

    def build_headers(self, account_name, target_url, cookies,
                      captured_headers=None):
        account_config = (
            self.auth_config.get("accounts", {}).get(account_name, {}) or {}
        )
        defaults = self.auth_config.get("defaults", {}) or {}
        config = {**defaults, **account_config}
        headers = {}

        # Cookie authentication: use cookies from this account's BrowserContext.
        cookie_mode = config.get("cookie", "auto")
        if cookie_mode is not False:
            value = cookie_header(cookies, target_url)
            if value:
                headers["Cookie"] = value

        # Bearer authentication: prefer an explicitly configured env token;
        # otherwise reuse Authorization observed on an in-scope browser request.
        bearer_env = config.get("bearer_token_env")
        token = None
        if bearer_env:
            import os
            token = os.environ.get(bearer_env)
            if token is None:
                raise ValueError(
                    f"Environment variable '{bearer_env}' is not set."
                )
        elif config.get("capture_authorization", True):
            token = (captured_headers or {}).get("authorization")

        authorization = bearer_header(token)
        if authorization:
            headers["Authorization"] = authorization

        # Explicit custom headers override automatically collected values.
        headers.update(resolve_header_values(config.get("custom_headers", {})))
        return headers


def capture_authorization_header(request, target_url):
    """Return Authorization only for requests to the exact target origin."""
    if not _same_origin(request.url, target_url):
        return None
    try:
        headers = request.headers
        value = headers.get("authorization")
        return value
    except Exception:
        return None
