def bearer_header(token):
    if not token:
        return None
    token = str(token).strip()
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"
