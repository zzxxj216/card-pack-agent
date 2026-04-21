"""Two-stage retrieval：先按 L2 硬过滤，再在候选集内按话题向量排序。

带时间衰减。人工否决过的 pack 被整包排除；card-level 多次否决会被打折。
"""
from __future__ import annotations

import math
from datetime import UTC, datetime

from ..feedback import card_reject_penalties, rejected_pack_ids
from ..memory.vector import COLLECTION_TOPIC, VectorHit, embed, vector_store
from ..schemas import L1, L2, Tier

# Exponential decay half-life (days). Tunable.
TIME_HALF_LIFE_DAYS = 90.0


def retrieve_similar_packs(
    topic: str,
    l1: L1 | None = None,
    l2: L2 | None = None,
    tier_gte: Tier | None = Tier.GOOD,
    top_k: int = 5,
) -> list[VectorHit]:
    """返回最相似的 top_k 个历史案例（只召回 tier >= tier_gte 的）。

    流程：
      1. 用 l2 作 payload_filter 做硬过滤（若提供）
      2. 向量检索 + 时间衰减重排
    """
    query_vec = embed(topic)

    payload_filter: dict[str, str] = {}
    if l1:
        payload_filter["l1"] = l1.value
    if l2:
        payload_filter["l2"] = l2.value
    if tier_gte:
        # Note: tier is not cleanly filterable via single match; in real mode use Qdrant
        # `should` with OR of tier values. For mock, post-filter below.
        pass

    hits = vector_store.search(
        collection=COLLECTION_TOPIC,
        vector=query_vec,
        top_k=top_k * 4,  # over-fetch, then filter + rerank + feedback-penalize
        payload_filter=payload_filter or None,
    )

    if tier_gte:
        order = {"bad": 0, "mid": 1, "good": 2, "viral": 3}
        threshold = order[tier_gte.value]
        hits = [h for h in hits if order.get(h.payload.get("tier", "bad"), 0) >= threshold]

    # Stage A: exclude human-rejected packs, apply card-reject penalty.
    # Derive pack_id from payload if present, else from the point id.
    rejected = rejected_pack_ids()
    penalties = card_reject_penalties()
    filtered: list[VectorHit] = []
    for h in hits:
        pid = h.payload.get("pack_id") or h.id
        if pid in rejected:
            continue
        penalty = penalties.get(pid, 1.0)
        if penalty != 1.0:
            h = VectorHit(id=h.id, score=h.score * penalty, payload=h.payload)
        filtered.append(h)

    # Time decay rerank
    now = datetime.now(UTC)
    reranked = []
    for h in filtered:
        created_at_iso = h.payload.get("created_at")
        if created_at_iso:
            try:
                created = datetime.fromisoformat(created_at_iso)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                age_days = (now - created).days
                decay = math.exp(-age_days / TIME_HALF_LIFE_DAYS)
                combined = h.score * decay
            except (ValueError, TypeError):
                combined = h.score
        else:
            combined = h.score
        reranked.append(VectorHit(id=h.id, score=combined, payload=h.payload))

    reranked.sort(key=lambda x: x.score, reverse=True)
    return reranked[:top_k]
