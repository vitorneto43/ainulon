import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg


SEED_PRIORITY = 10
SEED_DEPTH = 0


def connect():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def normalize_seed(url: str) -> tuple[str, str]:
    url = url.strip()

    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"URL inválida: {url}")

    if not parsed.hostname:
        raise ValueError(f"Domínio inválido: {url}")

    hostname = parsed.hostname.lower()

    return url, hostname


def load_seed_file(path: Path) -> list[str]:
    seeds = []

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        seeds.append(line)

    return seeds


def main():
    if len(sys.argv) != 2:
        print("Uso: python load_seeds.py /caminho/global_seeds.txt")
        raise SystemExit(1)

    seed_file = Path(sys.argv[1])

    if not seed_file.exists():
        print(f"Arquivo não encontrado: {seed_file}")
        raise SystemExit(1)

    seeds = load_seed_file(seed_file)

    added = 0
    existing = 0
    errors = 0

    with connect() as conn:
        with conn.cursor() as cur:
            for raw_url in seeds:
                try:
                    url, hostname = normalize_seed(raw_url)

                    cur.execute(
                        """
                        INSERT INTO domains (hostname)
                        VALUES (%s)
                        ON CONFLICT (hostname)
                        DO NOTHING;
                        """,
                        (hostname,),
                    )

                    cur.execute(
                        """
                        INSERT INTO urls (
                            url,
                            normalized_url,
                            status,
                            domain,
                            depth,
                            priority
                        )
                        VALUES (
                            %s,
                            %s,
                            'pending',
                            %s,
                            %s,
                            %s
                        )
                        ON CONFLICT (normalized_url)
                        DO NOTHING
                        RETURNING id;
                        """,
                        (
                            url,
                            url,
                            hostname,
                            SEED_DEPTH,
                            SEED_PRIORITY,
                        ),
                    )

                    row = cur.fetchone()

                    if row:
                        added += 1
                        print(f"🌱 Adicionada: {url}")
                    else:
                        existing += 1
                        print(f"↪ Já conhecida: {url}")

                except Exception as exc:
                    errors += 1
                    print(f"❌ {raw_url}: {exc}")

        conn.commit()

    print()
    print("=== Ainulon Global Seeds ===")
    print(f"Novas: {added}")
    print(f"Já existentes: {existing}")
    print(f"Erros: {errors}")
    print(f"Total processado: {len(seeds)}")


if __name__ == "__main__":
    main()