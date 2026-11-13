
import asyncio
import json
from datetime import datetime, timezone
from urllib.parse import (
    urlsplit,
    urlunsplit,
    parse_qsl,
    urlencode
)


SENSITIVE_KEYS = [
    "authorization",
    "cookie",
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "session"
]


def is_sensitive(key):
    key = key.lower().replace("-", "_")
    return any(item in key for item in SENSITIVE_KEYS)


def redact_data(data):
    if isinstance(data, dict):
        return {
            key: "[REDACTED]" if is_sensitive(key) else redact_data(value)
            for key, value in data.items()
        }

    if isinstance(data, list):
        return [redact_data(item) for item in data]

    return data


def clean_url(url):
    parts = urlsplit(url)
    query = []

    for key, value in parse_qsl(
        parts.query,
        keep_blank_values=True
    ):
        if is_sensitive(key):
            value = "[REDACTED]"

        query.append((key, value))

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        ""
    ))


def clean_headers(headers):
    result = {}

    for key, value in headers.items():
        if is_sensitive(key):
            result[key] = "[REDACTED]"
        else:
            result[key] = value

    return result


def get_json_body(raw_body, headers):
    if not raw_body:
        return None

    content_type = headers.get("content-type", "")

    if "json" not in content_type.lower():
        return None

    try:
        data = json.loads(raw_body)
        return redact_data(data)

    except (json.JSONDecodeError, TypeError):
        return None


class NetworkCollector:
    def __init__(self, allowed_hosts, max_response_body=100000):
        self.allowed_hosts = {
            host.lower()
            for host in allowed_hosts
            if host
        }

        self.max_response_body = max_response_body
        self.records = []
        self.records_by_request = {}

        # Stores sanitized headers when a request has not been recorded yet.
        self.request_header_overrides = {}

        self.pending_requests = set()
        self.pending_event = asyncio.Event()
        self.tasks = []

    def is_in_scope(self, url):
        parts = urlsplit(url)

        return (
            parts.scheme.lower() in ("http", "https")
            and parts.hostname is not None
            and parts.hostname.lower() in self.allowed_hosts
        )

    def update_request_headers(self, request, headers):
        safe_headers = clean_headers(headers)

        record = self.records_by_request.get(request)

        if record is not None:
            record["request_headers"] = safe_headers
        else:
            self.request_header_overrides[request] = safe_headers

    def attach(self, page):
        page.on(
            "request",
            lambda request: self.on_request(request, page.url)
        )

        page.on("response", self.on_response)
        page.on("requestfinished", self.on_request_finished)
        page.on("requestfailed", self.on_request_failed)

    def on_request(self, request, source_page):
        if not self.is_in_scope(request.url):
            return

        # Use updated headers if the authentication handler has supplied them.
        headers = self.request_header_overrides.pop(
            request,
            clean_headers(request.headers)
        )

        raw_body = request.post_data

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": request.method.upper(),
            "url": clean_url(request.url),
            "resource_type": request.resource_type,
            "source_page": clean_url(source_page),
            "request_headers": headers,
            "request_body": get_json_body(raw_body, request.headers),
            "response": None,
            "error": None
        }

        self.records.append(record)
        self.records_by_request[request] = record
        self.pending_requests.add(request)

    def on_response(self, response):
        record = self.records_by_request.get(response.request)

        if record is None:
            return

        headers = response.headers

        record["response"] = {
            "status": response.status,
            "headers": clean_headers(headers),
            "body": None
        }

        content_type = headers.get("content-type", "").lower()

        if "json" in content_type:
            task = asyncio.create_task(
                self.capture_response_body(response, record)
            )

            self.tasks.append(task)

    async def capture_response_body(self, response, record):
        try:
            content_length = response.headers.get("content-length")

            if content_length:
                if int(content_length) > self.max_response_body:
                    record["response"]["body_truncated"] = True
                    return

            body = await response.body()

            if len(body) > self.max_response_body:
                record["response"]["body_truncated"] = True
                return

            text = body.decode("utf-8")
            data = json.loads(text)

            record["response"]["body"] = redact_data(data)

        except Exception as error:
            record["response"]["body_error"] = str(error)

    def on_request_finished(self, request):
        self.pending_requests.discard(request)
        self.pending_event.set()

    def on_request_failed(self, request):
        record = self.records_by_request.get(request)

        if record is not None:
            record["error"] = request.failure

        self.pending_requests.discard(request)
        self.pending_event.set()

    async def wait_for_pending(self, timeout_ms=2000):
        deadline = (
            asyncio.get_running_loop().time()
            + timeout_ms / 1000
        )

        while self.pending_requests:
            remaining = (
                deadline - asyncio.get_running_loop().time()
            )

            if remaining <= 0:
                break

            self.pending_event.clear()

            try:
                await asyncio.wait_for(
                    self.pending_event.wait(),
                    timeout=remaining
                )

            except asyncio.TimeoutError:
                break

    async def wait_for_tasks(self):
        if self.tasks:
            await asyncio.gather(
                *self.tasks,
                return_exceptions=True
            )

            self.tasks.clear()
