"""Eval A — 分类准确率。

给定 holdout 话题，跑 Planner 只看分类结果，对比 gold label。

Metrics:
- l1_accuracy
- l2_accuracy
- l1_l2_joint_accuracy
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from card_pack_agent.agents.planner import plan
from card_pack_agent.schemas import ClarificationRequest, TopicInput

log = structlog.get_logger()

HOLDOUT_PATH = Path(__file__).resolve().parent.parent / "datasets" / "holdout.jsonl"


def _load_holdout() -> list[dict[str, Any]]:
    if not HOLDOUT_PATH.exists():
        return []
    return [json.loads(line) for line in HOLDOUT_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(limit: int | None = None) -> dict[str, Any]:
    samples = _load_holdout()
    if limit:
        samples = samples[:limit]

    l1_correct = 0
    l2_correct = 0
    joint_correct = 0
    details: list[dict[str, Any]] = []

    for s in samples:
        try:
            result, _meta = plan(
                TopicInput(raw_topic=s["topic"], extra_context=s.get("extra_context") or None),
            )
        except Exception as e:
            details.append({"id": s["id"], "status": "error", "error": str(e)})
            continue

        if isinstance(result, ClarificationRequest):
            details.append({"id": s["id"], "status": "clarification"})
            continue

        pred_l1 = _val(result.classification.l1)
        pred_l2 = _val(result.classification.l2)
        l1_ok = pred_l1 == s["gold_l1"]
        l2_ok = pred_l2 == s["gold_l2"]
        if l1_ok:
            l1_correct += 1
        if l2_ok:
            l2_correct += 1
        if l1_ok and l2_ok:
            joint_correct += 1

        details.append({
            "id": s["id"], "topic": s["topic"],
            "pred_l1": pred_l1, "pred_l2": pred_l2,
            "gold_l1": s["gold_l1"], "gold_l2": s["gold_l2"],
            "l1_ok": l1_ok, "l2_ok": l2_ok,
        })

    n = max(len(samples), 1)
    metrics = {
        "sample_size": len(samples),
        "l1_accuracy": l1_correct / n,
        "l2_accuracy": l2_correct / n,
        "l1_l2_joint_accuracy": joint_correct / n,
    }
    return {
        "suite": "classify",
        "metrics": metrics,
        "details": details,
        "summary": (
            f"L1={metrics['l1_accuracy']:.2%}, "
            f"L2={metrics['l2_accuracy']:.2%}, "
            f"joint={metrics['l1_l2_joint_accuracy']:.2%} "
            f"(n={n})"
        ),
    }


def _val(v: Any) -> str:
    return v.value if hasattr(v, "value") else str(v)
