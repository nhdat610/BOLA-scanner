from collector.normalizer import normalize_and_deduplicate


def make_record(method, url, body=None, response=None):
    return {
        "method": method,
        "url": url,
        "request_body": body,
        "response": response
    }


def test_remove_duplicate_requests():
    records = [
        make_record("GET", "https://example.com/api/books/1"),
        make_record("GET", "https://example.com/api/books/1"),
        make_record("GET", "https://example.com/api/books/2")
    ]

    result = normalize_and_deduplicate(records)

    assert len(result) == 2
    assert result[0]["occurrences"] == 2
    assert result[1]["occurrences"] == 1


def test_keep_requests_with_different_methods():
    records = [
        make_record("GET", "https://example.com/api/books/1"),
        make_record("DELETE", "https://example.com/api/books/1")
    ]

    result = normalize_and_deduplicate(records)

    assert len(result) == 2


def test_keep_requests_with_different_urls():
    records = [
        make_record("GET", "https://example.com/api/books/1"),
        make_record("GET", "https://example.com/api/books/2")
    ]

    result = normalize_and_deduplicate(records)

    assert len(result) == 2


def test_keep_requests_with_different_json_bodies():
    records = [
        make_record(
            "POST",
            "https://example.com/api/books",
            {"id": 1}
        ),
        make_record(
            "POST",
            "https://example.com/api/books",
            {"id": 2}
        )
    ]

    result = normalize_and_deduplicate(records)

    assert len(result) == 2


def test_remove_url_fragment():
    records = [
        make_record(
            "GET",
            "https://example.com/books#first"
        ),
        make_record(
            "GET",
            "https://example.com/books#second"
        )
    ]

    result = normalize_and_deduplicate(records)

    assert len(result) == 1
    assert result[0]["url"] == "https://example.com/books"


def test_same_json_body_with_different_key_order():
    records = [
        make_record(
            "POST",
            "https://example.com/api/books",
            {"id": 1, "name": "Book"}
        ),
        make_record(
            "POST",
            "https://example.com/api/books",
            {"name": "Book", "id": 1}
        )
    ]

    result = normalize_and_deduplicate(records)

    assert len(result) == 1
    assert result[0]["occurrences"] == 2


def test_merge_response_body():
    records = [
        make_record(
            "GET",
            "https://example.com/api/books/1",
            response={
                "status": 200,
                "headers": {},
                "body": None
            }
        ),
        make_record(
            "GET",
            "https://example.com/api/books/1",
            response={
                "status": 200,
                "headers": {},
                "body": {"id": 1}
            }
        )
    ]

    result = normalize_and_deduplicate(records)

    assert len(result) == 1
    assert result[0]["response"]["body"] == {"id": 1}