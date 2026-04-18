"""初始化 Postgres schema 和 Qdrant collections。

Usage:
    python scripts/init_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make package importable without install
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from card_pack_agent.config import settings  # noqa: E402
from card_pack_agent.logging import configure_logging  # noqa: E402
from card_pack_agent.memory.vector import vector_store  # noqa: E402


def init_postgres() -> None:
    if settings.is_mock:
        print("[mock] skipping Postgres init")
        return

    import psycopg

    sql_file = ROOT / "migrations" / "001_init.sql"
    sql = sql_file.read_text(encoding="utf-8")

    print(f"applying {sql_file.name} to {settings.postgres_dsn}")
    with psycopg.connect(settings.postgres_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql)
    print("postgres: ok")


def init_qdrant() -> None:
    print(f"ensuring Qdrant collections at {settings.qdrant_url}")
    vector_store.ensure_collections()
    print("qdrant: ok")


def main() -> None:
    configure_logging()
    init_postgres()
    init_qdrant()
    print("init_db: done")


if __name__ == "__main__":
    main()
