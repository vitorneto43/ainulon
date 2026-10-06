from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from db import connect


app = FastAPI(
    title="Ainulon Search API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class IndexRequest(BaseModel):
    url: HttpUrl


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ainulon-search-api",
    }


@app.get("/search")
def search(
    q: str = Query(
        ...,
        min_length=1,
        max_length=200,
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
    ),
):
    query = q.strip()

    sql = """
        WITH ranked AS (
            SELECT
                u.url,
                p.title,
                p.description,
                p.updated_at,
                ts_rank_cd(
                    setweight(
                        to_tsvector(
                            'simple',
                            COALESCE(p.title, '')
                        ),
                        'A'
                    )
                    ||
                    setweight(
                        to_tsvector(
                            'simple',
                            COALESCE(p.description, '')
                        ),
                        'B'
                    )
                    ||
                    setweight(
                        to_tsvector(
                            'simple',
                            COALESCE(p.content, '')
                        ),
                        'D'
                    ),
                    plainto_tsquery('simple', %s)
                ) AS text_score,
                CASE
                    WHEN LOWER(COALESCE(p.title, '')) = LOWER(%s)
                        THEN 2.0
                    WHEN LOWER(COALESCE(p.title, '')) LIKE LOWER(%s) || '%%'
                        THEN 0.8
                    WHEN LOWER(COALESCE(p.title, '')) LIKE '%%' || LOWER(%s) || '%%'
                        THEN 0.4
                    ELSE 0.0
                END AS title_boost,
                CASE
                    WHEN LOWER(u.url) LIKE '%%' || LOWER(%s) || '%%'
                        THEN 0.1
                    ELSE 0.0
                END AS url_boost,
                ts_headline(
                    'simple',
                    CONCAT_WS(
                        ' ',
                        NULLIF(p.description, ''),
                        COALESCE(p.content, '')
                    ),
                    plainto_tsquery('simple', %s),
                    'MaxWords=30, MinWords=10, StartSel=<mark>, StopSel=</mark>'
                ) AS snippet
            FROM pages p
            JOIN urls u
                ON u.id = p.url_id
            WHERE
                (
                    setweight(
                        to_tsvector(
                            'simple',
                            COALESCE(p.title, '')
                        ),
                        'A'
                    )
                    ||
                    setweight(
                        to_tsvector(
                            'simple',
                            COALESCE(p.description, '')
                        ),
                        'B'
                    )
                    ||
                    setweight(
                        to_tsvector(
                            'simple',
                            COALESCE(p.content, '')
                        ),
                        'D'
                    )
                ) @@ plainto_tsquery('simple', %s)
        )
        SELECT
            url,
            title,
            description,
            (
                text_score
                + title_boost
                + url_boost
            ) AS score,
            snippet
        FROM ranked
        WHERE text_score >= 0.005
        ORDER BY
            score DESC,
            updated_at DESC
        LIMIT %s;
    """

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    query,
                    query,
                    query,
                    query,
                    query,
                    query,
                    query,
                    limit,
                ),
            )

            results = cur.fetchall()

    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


@app.post("/index")
def add_url(request: IndexRequest):
    url = str(request.url)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO urls (
                    url,
                    normalized_url,
                    status
                )
                VALUES (%s, %s, 'pending')
                ON CONFLICT (normalized_url)
                DO UPDATE SET
                    status = CASE
                        WHEN urls.status = 'indexed'
                        THEN urls.status
                        ELSE 'pending'
                    END
                RETURNING id, status;
                """,
                (
                    url,
                    url,
                ),
            )

            row = cur.fetchone()

        conn.commit()

    return {
        "url": url,
        "id": row["id"],
        "status": row["status"],
    }