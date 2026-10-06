import time
from urllib.parse import parse_qs, urlparse
from url_utils import normalize_url

import requests
from langdetect import LangDetectException, detect

from db import (
    enqueue_links,
    find_other_url_id,
    get_hostname,
    get_next_pending_url,
    mark_blocked_robots,
    mark_ignored_url,
    mark_redirect_duplicate,
    save_error,
    save_page,
)
from parser import parse_html
from robots import USER_AGENT, can_crawl


TIMEOUT = 15
MAX_CONTENT_LENGTH = 5_000_000

IGNORED_QUERY_PARAMS = {
    "search",
    "s",
    "query",
    "q",
}




def should_ignore_url(url: str) -> bool:
    parsed = urlparse(url)

    query_params = {
        key.lower()
        for key in parse_qs(
            parsed.query,
            keep_blank_values=True,
        )
    }

    return bool(
        query_params & IGNORED_QUERY_PARAMS
    )


def detect_language(
    html_language: str | None,
    content: str,
) -> str:
    if html_language:
        return (
            html_language
            .strip()
            .lower()
            .split("-")[0]
        )

    if len(content.strip()) < 50:
        return "und"

    try:
        return detect(content)
    except LangDetectException:
        return "und"


def crawl(
    url_id: int,
    url: str,
    depth: int,
) -> None:
    try:
        url = normalize_url(url)

        print(
            f"🔎 Ainulon visitando: {url} "
            f"(depth={depth})"
        )

        if should_ignore_url(url):
            mark_ignored_url(
                url_id,
                "Página de busca interna",
            )

            print(
                f"⏭️ URL de busca ignorada: {url}"
            )

            return

        if not can_crawl(url):
            mark_blocked_robots(url_id)

            print(
                "⛔ robots.txt não permite "
                "o rastreamento."
            )

            return

        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,"
                    "application/xhtml+xml"
                ),
            },
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            "",
        )

        if "text/html" not in content_type.lower():
            raise ValueError(
                f"Conteúdo não HTML: {content_type}"
            )

        if len(response.content) > MAX_CONTENT_LENGTH:
            raise ValueError(
                "Página excede o limite de tamanho."
            )

        final_url = normalize_url(
            response.url
        )

        if should_ignore_url(final_url):
            mark_ignored_url(
                url_id,
                "Redirect para página de busca interna",
            )

            print(
                f"⏭️ Redirect para busca ignorado: "
                f"{url} -> {final_url}"
            )

            return

        existing_final_id = find_other_url_id(
            final_url,
            url_id,
        )

        if (
            existing_final_id is not None
            and existing_final_id != url_id
        ):
            mark_redirect_duplicate(
                url_id,
                final_url,
            )

            print(
                f"↪️ Redirect já conhecido: "
                f"{url} -> {final_url}"
            )

            return

        page = parse_html(
            response.text,
            final_url,
        )

        language = detect_language(
            page.html_language,
            page.content,
        )

        save_page(
            url_id=url_id,
            url=final_url,
            normalized_url=final_url,
            http_status=response.status_code,
            content_type=content_type,
            title=page.title,
            description=page.description,
            content=page.content,
            canonical_url=page.canonical_url,
            language=language,
        )

        source_domain = get_hostname(
            final_url
        )

        enqueue_links(
            source_url_id=url_id,
            source_depth=depth,
            source_domain=source_domain,
            links=page.links,
        )

        print("✅ Página indexada.")
        print(f"ID: {url_id}")
        print(f"Título: {page.title}")
        print(f"Idioma: {language}")
        print(
            f"Links considerados: "
            f"{len(page.links)}"
        )

    except Exception as exc:
        save_error(
            url_id,
            str(exc),
        )

        print(
            f"❌ Erro ao rastrear "
            f"{url}: {exc}"
        )


def main() -> None:
    print("🤖 Ainulon crawler iniciado.")

    while True:
        item = get_next_pending_url()

        if item is None:
            time.sleep(5)
            continue

        url_id, url, depth = item

        crawl(
            url_id=url_id,
            url=url,
            depth=depth,
        )

        time.sleep(1)


if __name__ == "__main__":
    main()