from crawler.crawler import normalize_url, is_in_scope


ALLOWED_DOMAINS = {"books.toscrape.com"}


def test_normalize_url_removes_fragment():
    url = "https://books.toscrape.com/catalogue/page-1.html#reviews"

    result = normalize_url(url)

    assert result == "https://books.toscrape.com/catalogue/page-1.html"


def test_normalize_url_adds_root_path():
    url = "https://books.toscrape.com"

    result = normalize_url(url)

    assert result == "https://books.toscrape.com/"


def test_is_in_scope_accepts_allowed_domain():
    url = "https://books.toscrape.com/catalogue/page-1.html"

    assert is_in_scope(url, ALLOWED_DOMAINS)


def test_is_in_scope_rejects_external_domain():
    url = "https://example.com/"

    assert not is_in_scope(url, ALLOWED_DOMAINS)


def test_is_in_scope_rejects_similar_domain():
    url = "https://books.toscrape.com.example.com/"

    assert not is_in_scope(url, ALLOWED_DOMAINS)