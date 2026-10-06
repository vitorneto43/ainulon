-- Ainulon - Crawl Control v1

CREATE TABLE IF NOT EXISTS domains (
    id BIGSERIAL PRIMARY KEY,
    hostname TEXT NOT NULL UNIQUE,

    last_crawled_at TIMESTAMPTZ,
    next_allowed_at TIMESTAMPTZ,

    crawl_delay_seconds NUMERIC(6,2) NOT NULL DEFAULT 2.0,
    max_pages INTEGER NOT NULL DEFAULT 500,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


ALTER TABLE urls
    ADD COLUMN IF NOT EXISTS domain TEXT,
    ADD COLUMN IF NOT EXISTS depth INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100,
    ADD COLUMN IF NOT EXISTS discovered_from_url_id BIGINT;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_urls_discovered_from'
    ) THEN
        ALTER TABLE urls
        ADD CONSTRAINT fk_urls_discovered_from
        FOREIGN KEY (discovered_from_url_id)
        REFERENCES urls(id)
        ON DELETE SET NULL;
    END IF;
END $$;


-- Extrai hostname das URLs já existentes.
UPDATE urls
SET domain = LOWER(
    SUBSTRING(
        url
        FROM '^[a-zA-Z]+://([^/:?#]+)'
    )
)
WHERE domain IS NULL;


-- Registra os domínios que já conhecemos.
INSERT INTO domains (hostname)
SELECT DISTINCT domain
FROM urls
WHERE domain IS NOT NULL
ON CONFLICT (hostname) DO NOTHING;


CREATE INDEX IF NOT EXISTS idx_urls_queue
    ON urls (
        status,
        priority,
        depth,
        discovered_at
    );


CREATE INDEX IF NOT EXISTS idx_urls_domain_status
    ON urls (
        domain,
        status
    );


CREATE INDEX IF NOT EXISTS idx_domains_next_allowed
    ON domains (
        next_allowed_at
    );