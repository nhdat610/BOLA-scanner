def cookie_header(cookies, target_url):
    from urllib.parse import urlsplit
    target = urlsplit(target_url)
    pairs = []
    for item in cookies:
        domain = item.get("domain", "").lstrip(".").lower()
        host = (target.hostname or "").lower()
        if domain and (host == domain or host.endswith("." + domain)):
            pairs.append(f"{item['name']}={item['value']}")
    return "; ".join(pairs) if pairs else None
