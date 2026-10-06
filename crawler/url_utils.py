from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            "A URL precisa começar com http:// ou https://"
        )

    scheme = parsed.scheme.lower()

    hostname = (
        parsed.hostname.lower()
        if parsed.hostname
        else ""
    )

    port = parsed.port

    if (
        (scheme == "http" and port == 80)
        or
        (scheme == "https" and port == 443)
    ):
        port = None

    netloc = hostname

    if port is not None:
        netloc = f"{hostname}:{port}"

    path = parsed.path or "/"

    normalized = parsed._replace(
        scheme=scheme,
        netloc=netloc,
        path=path,
        fragment="",
    )

    return urlunparse(normalized)