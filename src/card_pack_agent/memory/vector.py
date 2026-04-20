"""Qdrant 向量检索。支持 topic / pack / card 三路。

Mock mode 用朴素 in-memory list + hash-based fake embedding。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from ..config import settings

log = structlog.get_logger()


# --- Collections ---

COLLECTION_TOPIC = "topic_vectors"
COLLECTION_PACK = "pack_vectors"
COLLECTION_CARD = "card_vectors"

EMBEDDING_DIM = 768  # stub; replace with real embedding dim when wired


@dataclass
class VectorHit:
    id: str
    score: float
    payload: dict[str, Any]


class VectorStore:
    """向量库薄封装。"""

    def __init__(self) -> None:
        self._client: Any = None
        self._mock_store: dict[str, list[tuple[str, list[float], dict[str, Any]]]] = {
            COLLECTION_TOPIC: [],
            COLLECTION_PACK: [],
            COLLECTION_CARD: [],
        }

    def _real_client(self) -> Any:
        if self._client is None:
            settings.require_real_mode("VectorStore")
            from qdrant_client import QdrantClient
            if settings.qdrant_url and not settings.qdrant_url.startswith("http://localhost"):
                # Remote Qdrant (prod)
                self._client = QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key or None,
                )
            else:
                # Local file-based Qdrant (dev) — no server needed
                local_path = str(Path(settings.knowledge_path).parent / "qdrant_data")
                log.info("vector.using_local_storage", path=local_path)
                self._client = QdrantClient(path=local_path)
        return self._client

    # --- Init ---

    def ensure_collections(self) -> None:
        """idempotent collection create. Called from scripts/init_db.py."""
        if settings.is_mock:
            log.info("vector.ensure_collections.mock")
            return
        from qdrant_client.models import Distance, VectorParams
        client = self._real_client()
        for col in (COLLECTION_TOPIC, COLLECTION_PACK, COLLECTION_CARD):
            if not client.collection_exists(col):
                client.create_collection(
                    collection_name=col,
                    vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
                )
                log.info("vector.collection_created", collection=col)

    # --- Upsert ---

    def upsert(
        self,
        collection: str,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        if settings.is_mock:
            self._mock_store[collection].append((point_id, vector, payload))
            return
        import uuid as _uuid
        from qdrant_client.models import PointStruct
        # Local Qdrant requires UUID ids
        try:
            uid = _uuid.UUID(point_id)
        except ValueError:
            uid = _uuid.uuid5(_uuid.NAMESPACE_URL, point_id)
        self._real_client().upsert(
            collection_name=collection,
            points=[PointStruct(id=str(uid), vector=vector, payload=payload)],
        )

    # --- Search ---

    def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        payload_filter: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        if settings.is_mock:
            return self._mock_search(collection, vector, top_k, payload_filter)

        from qdrant_client.models import FieldCondition, Filter, MatchValue
        flt = None
        if payload_filter:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in payload_filter.items()
            ]
            flt = Filter(must=conditions)

        try:
            results = self._real_client().query_points(
                collection_name=collection,
                query=vector,
                limit=top_k,
                query_filter=flt,
            ).points
        except Exception as exc:
            log.warning("vector.search.fallback_empty", error=str(exc)[:200])
            return []
        return [
            VectorHit(id=str(r.id), score=r.score, payload=r.payload or {})
            for r in results
        ]

    def _mock_search(
        self,
        collection: str,
        vector: list[float],
        top_k: int,
        payload_filter: dict[str, Any] | None,
    ) -> list[VectorHit]:
        """朴素暴力检索 + 可选 payload filter。"""
        rows = self._mock_store[collection]
        if payload_filter:
            rows = [r for r in rows if all(r[2].get(k) == v for k, v in payload_filter.items())]
        scored = [
            (pid, _cosine(vector, v), payload)
            for pid, v, payload in rows
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            VectorHit(id=pid, score=score, payload=payload)
            for pid, score, payload in scored[:top_k]
        ]


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb + 1e-12)


# --- Embedding (stub — replace with real model in Phase 3) ---

def fake_embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic hash-based embedding. Use for mock mode only."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    # Expand hash deterministically to `dim` floats in [-1, 1]
    out: list[float] = []
    seed = h
    while len(out) < dim:
        seed = hashlib.sha256(seed).digest()
        for b in seed:
            out.append((b / 127.5) - 1.0)
            if len(out) >= dim:
                break
    return out


def embed(text: str) -> list[float]:
    """Real embedding hook. For now delegates to fake_embed.

    Phase 3: swap to Anthropic embedding API or a hosted embedding model.
    """
    return fake_embed(text)


# Module-level singleton
vector_store = VectorStore()
