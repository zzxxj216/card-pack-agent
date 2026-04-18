"""Eval C — 端到端生成评测。

对 holdout 每个话题：
- 跑完整 pipeline (Planner → Generator → Evaluator)
- 记录 Evaluator judge 分数
- 记录是否通过 Evaluator 规则检查
- 记录单包内部视觉重复情况

Metrics:
- avg_overall_score:   judge overall_score 平均
- evaluator_pass_rate: verdict==PASS 的比例
- avg_style_consistency
- avg_rule_adherence
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from card_pack_agent.orchestrator import run as orchestrate
from card_pack_agent.schemas import TopicInput

HOLDOUT_PATH = Path(__file__).resolve().parent.parent / "datasets" / "holdout.jsonl"


def _load_holdout() -> list[dict[str, Any]]:
    if not HOLDOUT_PATH.exists():
        return []
    return [json.loads(line) for line in HOLDOUT_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(limit: int | None = None) -> dict[str, Any]:
    samples = _load_holdout()
    if limit:
        samples = samples[:limit]

    pass_count = 0
    fail_count = 0
    overall_scores: list[float] = []
    style_scores: list[float] = []
    rule_scores: list[float] = []
    details: list[dict[str, Any]] = []

    for s in samples:
        try:
            result = orchestrate(
                TopicInput(raw_topic=s["topic"]),
                hint_l1=s.get("gold_l1"),
                hint_l2=s.get("gold_l2"),
                generate_images=False,
                persist=False,
            )
        except Exception as e:
            details.append({"id": s["id"], "error": str(e)})
            fail_count += 1
            continue

        if not result.pack:
            details.append({"id": s["id"], "status": "no_pack", "clarification": bool(result.clarification)})
            continue

        report = result.evaluator_report
        if report.passed:
            pass_count += 1
        else:
            fail_count += 1

        js = report.judge_scores or {}
        if "overall_score" in js:
            overall_scores.append(js["overall_score"])
        if "style_consistency" in js:
            style_scores.append(js["style_consistency"])
        if "rule_adherence" in js:
            rule_scores.append(js["rule_adherence"])

        details.append({
            "id": s["id"],
            "verdict": report.verdict.value,
            "issues": [{"code": i.code, "severity": i.severity.value} for i in report.issues],
            "overall_score": js.get("overall_score"),
        })

    n = max(len(samples), 1)
    metrics = {
        "sample_size": len(samples),
        "evaluator_pass_rate": pass_count / n,
        "fail_rate": fail_count / n,
        "avg_overall_score": _mean(overall_scores),
        "avg_style_consistency": _mean(style_scores),
        "avg_rule_adherence": _mean(rule_scores),
    }
    return {
        "suite": "generate",
        "metrics": metrics,
        "details": details,
        "summary": (
            f"pass_rate={metrics['evaluator_pass_rate']:.2%}, "
            f"judge={metrics['avg_overall_score']:.2f}"
        ),
    }


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0
