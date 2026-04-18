"""Web tools — 供 Planner 调用。

Phase 2+ 再接真实 search。前期 Planner 用户已经提供 topic，不强依赖。
"""
from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger()


def fetch_url(url: str, *, timeout: float = 10.0) -> str:
    """Fetch text content of a URL. Returns best-effort plaintext."""
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            r = client.get(url, headers={"User-Agent": "card-pack-agent/0.1"})
            r.raise_for_status()
            return r.text[:50_000]  # hard cap
    except Exception as e:
        log.warning("fetch_url.failed", url=url, error=str(e))
        return ""


def web_search(query: str, *, top_k: int = 5) -> list[dict[str, str]]:
    """Stub. Wire to SerpAPI / Brave / Tavily in Phase 2."""
    log.info("web_search.stub", query=query, top_k=top_k)
    return []
