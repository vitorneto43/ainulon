import hashlib
import os
from urllib.parse import urlparse
from url_utils import normalize_url

import psycopg


MAX_DEPTH = 2
MAX_PAGES_PER_DOMAIN = 100
MAX_PENDING_GLOBAL = 20_000
MAX_NEW_DOMAINS_PER_PAGE = 5


def connect():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def get_hostname(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname.lower() if parsed.hostname else ""


def get_next_pending_url() -> tuple[int, str, int] | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH candidate AS (
                    SELECT u.id
                    FROM urls u
                    LEFT JOIN domains d
                        ON d.hostname = u.domain
                    WHERE
                        u.status = 'pending'
                        AND u.depth <= %s
                        AND (
                            d.next_allowed_at IS NULL
                            OR d.next_allowed_at <= NOW()
                        )
                    ORDER BY
                        u.priority ASC,
                        u.depth ASC,
                        u.discovered_at ASC
                    LIMIT 1
                    FOR UPDATE OF u SKIP LOCKED
                )
                UPDATE urls u
                SET status = 'crawling'
                FROM candidate c
                WHERE u.id = c.id
                RETURNING
                    u.id,
                    u.url,
                    u.depth;
                """,
                (MAX_DEPTH,),
            )

            row = cur.fetchone()

        conn.commit()

    if row is None:
        return None

    return row[0], row[1], row[2]


def enqueue_links(
    source_url_id: int,
    source_depth: int,
    source_domain: str,
    links: list[tuple[str, str]],
) -> None:
    next_depth = source_depth + 1

    if next_depth > MAX_DEPTH:
        return

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM urls
                WHERE status = 'pending';
                """
            )

            pending_count = cur.fetchone()[0]

            if pending_count >= MAX_PENDING_GLOBAL:
                return

            cur.execute(
                """
                SELECT DISTINCT domain
                FROM urls
                WHERE domain IS NOT NULL;
                """
            )

            known_domains = {
                row[0]
                for row in cur.fetchall()
                if row[0]
            }

            domain_counts: dict[str, int] = {}

            cur.execute(
                """
                SELECT domain, COUNT(*)
                FROM urls
                WHERE domain IS NOT NULL
                GROUP BY domain;
                """
            )

            for domain, count in cur.fetchall():
                domain_counts[domain] = count

            new_domains_added = 0

            for target_url, anchor_text in links:
                if pending_count >= MAX_PENDING_GLOBAL:
                    break

                try:
                    target_url = normalize_url(target_url)
                except ValueError:
                    continue

                target_domain = get_hostname(target_url)

                if not target_domain:
                    continue

                current_count = domain_counts.get(
                    target_domain,
                    0,
                )

                if current_count >= MAX_PAGES_PER_DOMAIN:
                    continue

                is_same_domain = (
                    target_domain == source_domain
                )

                is_new_domain = (
                    target_domain not in known_domains
                )

                if (
                    is_new_domain
                    and not is_same_domain
                    and new_domains_added
                    >= MAX_NEW_DOMAINS_PER_PAGE
                ):
                    continue

                priority = 50 if is_same_domain else 300

                cur.execute(
                    """
                    INSERT INTO domains (
                        hostname,
                        crawl_delay_seconds,
                        max_pages
                    )
                    VALUES (%s, 3.0, %s)
                    ON CONFLICT (hostname)
                    DO NOTHING;
                    """,
                    (
                        target_domain,
                        MAX_PAGES_PER_DOMAIN,
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO urls (
                        url,
                        normalized_url,
                        status,
                        domain,
                        depth,
                        priority,
                        discovered_from_url_id
                    )
                    VALUES (
                        %s,
                        %s,
                        'pending',
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    ON CONFLICT (normalized_url)
                    DO NOTHING
                    RETURNING id;
                    """,
                    (
                        target_url,
                        target_url,
                        target_domain,
                        next_depth,
                        priority,
                        source_url_id,
                    ),
                )

                row = cur.fetchone()

                if row:
                    pending_count += 1
                    domain_counts[target_domain] = (
                        current_count + 1
                    )

                    if is_new_domain:
                        known_domains.add(
                            target_domain
                        )

                        if not is_same_domain:
                            new_domains_added += 1

                cur.execute(
                    """
                    INSERT INTO links (
                        source_url_id,
                        target_url,
                        anchor_text
                    )
                    VALUES (%s, %s, %s);
                    """,
                    (
                        source_url_id,
                        target_url,
                        anchor_text,
                    ),
                )

        conn.commit()


def save_page(
    url_id: int,
    url: str,
    normalized_url: str,
    http_status: int,
    content_type: str,
    title: str | None,
    description: str | None,
    content: str,
    canonical_url: str | None,
    language: str,
) -> None:
    content_hash = hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()

    domain = get_hostname(url)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE urls
                SET
                    url = %s,
                    normalized_url = %s,
                    status = 'indexed',
                    domain = %s,
                    last_crawled_at = NOW(),
                    http_status = %s,
                    content_type = %s,
                    crawl_attempts = crawl_attempts + 1,
                    crawl_error = NULL
                WHERE id = %s;
                """,
                (
                    url,
                    normalized_url,
                    domain,
                    http_status,
                    content_type,
                    url_id,
                ),
            )

            cur.execute(
                """
                INSERT INTO pages (
                    url_id,
                    title,
                    description,
                    content,
                    language,
                    canonical_url,
                    content_hash,
                    indexed_at,
                    updated_at,
                    search_vector
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW(),
                    NOW(),
                    to_tsvector(
                        'simple',
                        COALESCE(%s, '') || ' ' ||
                        COALESCE(%s, '') || ' ' ||
                        COALESCE(%s, '')
                    )
                )
                ON CONFLICT (url_id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    content = EXCLUDED.content,
                    language = EXCLUDED.language,
                    canonical_url = EXCLUDED.canonical_url,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = NOW(),
                    search_vector = EXCLUDED.search_vector;
                """,
                (
                    url_id,
                    title,
                    description,
                    content,
                    language,
                    canonical_url,
                    content_hash,
                    title,
                    description,
                    content,
                ),
            )

            cur.execute(
                """
                INSERT INTO domains (
                    hostname,
                    last_crawled_at,
                    next_allowed_at
                )
                VALUES (
                    %s,
                    NOW(),
                    NOW() + INTERVAL '3 seconds'
                )
                ON CONFLICT (hostname)
                DO UPDATE SET
                    last_crawled_at = NOW(),
                    next_allowed_at = NOW() + INTERVAL '3 seconds',
                    updated_at = NOW();
                """,
                (domain,),
            )

        conn.commit()


def mark_blocked_robots(url_id: int) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE urls
                SET
                    status = 'blocked_robots',
                    last_crawled_at = NOW()
                WHERE id = %s;
                """,
                (url_id,),
            )

        conn.commit()


def save_error(url_id: int, error: str) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE urls
                SET
                    status = 'error',
                    crawl_attempts = crawl_attempts + 1,
                    crawl_error = %s,
                    last_crawled_at = NOW()
                WHERE id = %s;
                """,
                (
                    error[:2000],
                    url_id,
                ),
            )

        conn.commit()

def find_other_url_id(
    url: str,
    current_url_id: int,
) -> int | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM urls
                WHERE id <> %s
                  AND (
                      url = %s
                      OR normalized_url = %s
                  )
                LIMIT 1;
                """,
                (
                    current_url_id,
                    url,
                    url,
                ),
            )

            row = cur.fetchone()

    return row[0] if row else None
def mark_redirect_duplicate(
    url_id: int,
    final_url: str,
) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE urls
                SET
                    status = 'redirect_duplicate',
                    last_crawled_at = NOW(),
                    crawl_error = %s
                WHERE id = %s;
                """,
                (
                    (
                        "Redirect para URL "
                        f"já conhecida: {final_url}"
                    ),
                    url_id,
                ),
            )

        conn.commit()


def mark_ignored_url(
    url_id: int,
    reason: str,
) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE urls
                SET
                    status = 'ignored',
                    last_crawled_at = NOW(),
                    crawl_error = %s
                WHERE id = %s;
                """,
                (
                    reason[:2000],
                    url_id,
                ),
            )

        conn.commit()

    return row[0] if row else None