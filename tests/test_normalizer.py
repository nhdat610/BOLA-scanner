from collector.normalizer import normalize_and_deduplicate


def make_record(url):
    return {
        "method": "GET",
        "url": url,
        "request_body": None,
        "response": None
    }


def test_remove_duplicate_requests():
    records = [
        make_record("https://example.com/api/books/1"),
        make_record("https://example.com/api/books/1"),
        make_record("https://example.com/api/books/2")
    ]

    result = normalize_and_deduplicate(records)

    assert len(result) == 2
    assert result[0]["occurrences"] == 2
    assert result[1]["occurrences"] == 1


def test_remove_url_fragment():
    records = [
        make_record("https://example.com/books#first")
    ]

    result = normalize_and_deduplicate(records)

    assert result[0]["url"] == "https://example.com/books"
    assert result[0]["path"] == "/books"
