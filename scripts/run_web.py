"""启动评测 UI (FastAPI + Jinja2)。

Usage:
    python scripts/run_web.py                    # default: 127.0.0.1:8000
    python scripts/run_web.py --host 0.0.0.0     # LAN
    python scripts/run_web.py --port 8080
    python scripts/run_web.py --reload           # dev auto-reload
"""
from __future__ import annotations

import sys
from pathlib import Path

import click
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@click.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8000, type=int)
@click.option("--reload/--no-reload", default=False)
def main(host: str, port: int, reload: bool) -> None:
    uvicorn.run(
        "card_pack_agent.web.app:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[str(ROOT / "src" / "card_pack_agent" / "web")] if reload else None,
    )


if __name__ == "__main__":
    main()
