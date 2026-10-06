CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS urls (
    id BIGSERIAL PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    normalized_url TEXT NOT NULL UNIQUE,

    status VARCHAR(30) NOT NULL DEFAULT 'pending',

    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_crawled_at TIMESTAMPTZ,
    next_crawl_at TIMESTAMPTZ,

    http_status INTEGER,
    content_type VARCHAR(255),

    crawl_attempts INTEGER NOT NULL DEFAULT 0,
    crawl_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_urls_status
    ON urls(status);

CREATE INDEX IF NOT EXISTS idx_urls_next_crawl
    ON urls(next_crawl_at);


CREATE TABLE IF NOT EXISTS pages (
    id BIGSERIAL PRIMARY KEY,
    url_id BIGINT NOT NULL UNIQUE
        REFERENCES urls(id)
        ON DELETE CASCADE,

    title TEXT,
    description TEXT,
    content TEXT,

    language VARCHAR(20),

    canonical_url TEXT,

    content_hash VARCHAR(128),

    indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    search_vector TSVECTOR
);

CREATE INDEX IF NOT EXISTS idx_pages_search_vector
    ON pages
    USING GIN(search_vector);

CREATE INDEX IF NOT EXISTS idx_pages_title_trgm
    ON pages
    USING GIN(title gin_trgm_ops);


CREATE TABLE IF NOT EXISTS links (
    id BIGSERIAL PRIMARY KEY,

    source_url_id BIGINT NOT NULL
        REFERENCES urls(id)
        ON DELETE CASCADE,

    target_url TEXT NOT NULL,

    anchor_text TEXT,

    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_links_source
    ON links(source_url_id);


CREATE TABLE IF NOT EXISTS crawl_events (
    id BIGSERIAL PRIMARY KEY,

    url_id BIGINT
        REFERENCES urls(id)
        ON DELETE SET NULL,

    event_type VARCHAR(50) NOT NULL,

    details JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);