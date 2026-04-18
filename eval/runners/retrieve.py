"""Eval B — 检索质量。

对 holdout 每个话题，跑 two-stage retrieval，检查 top-K 里是否包含
tier >= good 的同机制（L2）案例。

Metrics:
- hit_at_5_good_plus:  至少一个 tier>=good 的结果
- l2_match_rate:       top-K 里 L2 与 query hint 一致的比例
- mean_score:          top-1 的 cosine
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from card_pack_agent.schemas import L1, L2, Tier
from card_pack_agent.tools.retrieve import retrieve_similar_packs

HOLDOUT_PATH = Path(__file__).resolve().parent.parent / "datasets" / "holdout.jsonl"


def _load_holdout() -> list[dict[str, Any]]:
    if not HOLDOUT_PATH.exists():
        return []
    return [json.loads(line) for line in HOLDOUT_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(limit: int | None = None) -> dict[str, Any]:
    samples = _load_holdout()
    if limit:
        samples = samples[:limit]

    hit_count = 0
    l2_match_total = 0
    l2_match_denom = 0
    top1_scores: list[float] = []
    details: list[dict[str, Any]] = []

    for s in samples:
        try:
            l1_enum = L1(s["gold_l1"])
            l2_enum = L2(s["gold_l2"])
        except ValueError:
            continue

        hits = retrieve_similar_packs(
            topic=s["topic"],
            l1=l1_enum,
            l2=l2_enum,
            tier_gte=Tier.GOOD,
            top_k=5,
        )

        good_hit = len(hits) > 0
        if good_hit:
            hit_count += 1
            top1_scores.append(hits[0].score)

        for h in hits:
            l2_match_denom += 1
            if h.payload.get("l2") == s["gold_l2"]:
                l2_match_total += 1

        details.append({
            "id": s["id"],
            "topic": s["topic"],
            "n_hits": len(hits),
            "top1_tier": hits[0].payload.get("tier") if hits else None,
            "top1_l2": hits[0].payload.get("l2") if hits else None,
        })

    n = max(len(samples), 1)
    metrics = {
        "sample_size": len(samples),
        "hit_at_5_good_plus": hit_count / n,
        "l2_match_rate": l2_match_total / max(l2_match_denom, 1),
        "mean_top1_score": sum(top1_scores) / len(top1_scores) if top1_scores else 0.0,
    }
    return {
        "suite": "retrieve",
        "metrics": metrics,
        "details": details,
        "summary": (
            f"hit@5={metrics['hit_at_5_good_plus']:.2%}, "
            f"l2_match={metrics['l2_match_rate']:.2%}, "
            f"top1={metrics['mean_top1_score']:.3f}"
        ),
    }
