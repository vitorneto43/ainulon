from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

MAX_LINKS_PER_PAGE = 100


@dataclass
class ParsedPage:
    title: str | None
    description: str | None
    content: str
    canonical_url: str | None
    html_language: str | None
    links: list[tuple[str, str]]


def is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"}


def parse_html(html: str | bytes, base_url: str) -> ParsedPage:
    soup = BeautifulSoup(html, "html.parser")

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    description = None
    description_tag = soup.find(
        "meta",
        attrs={"name": "description"},
    )

    if description_tag:
        description = description_tag.get("content")

    canonical_url = None
    canonical = soup.find(
        "link",
        attrs={"rel": "canonical"},
    )

    if canonical and canonical.get("href"):
        canonical_url = urljoin(
            base_url,
            canonical["href"],
        )

    html_language = None

    if soup.html:
        raw_language = soup.html.get("lang")

        if raw_language:
            html_language = (
                raw_language
                .strip()
                .lower()
                .split("-")[0]
            )

    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "template",
            "iframe",
        ]
    ):
        tag.decompose()

    content = " ".join(
        soup.get_text(
            separator=" ",
            strip=True,
        ).split()
    )

    links: list[tuple[str, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        if len(links) >= MAX_LINKS_PER_PAGE:
            break

        target = urljoin(
            base_url,
            anchor["href"],
        )

        if not is_http_url(target):
            continue

        target = target.split("#", 1)[0]

        if target in seen:
            continue

        seen.add(target)

        anchor_text = " ".join(
            anchor.get_text(
                separator=" ",
                strip=True,
            ).split()
        )

        links.append(
            (
                target,
                anchor_text,
            )
        )

    return ParsedPage(
        title=title,
        description=description,
        content=content,
        canonical_url=canonical_url,
        html_language=html_language,
        links=links,
    )