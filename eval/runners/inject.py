"""Eval D — 经验注入评测。

对同一批 holdout 话题，分别在四种知识注入设定下跑生成，看 judge 分数是否单调上升。

四档设定：
- bare:     不加载任何 .md (裸跑)
- global:   只加载 global_style_guide + global_anti_patterns + taxonomy
- category: 加上对应 category playbook
- all:      加上 experience_log

如果"更多知识反而分数下降" → 说明某份文档注入效果为负（噪声 > 信号）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from card_pack_agent.orchestrator import run as orchestrate
from card_pack_agent.schemas import TopicInput

HOLDOUT_PATH = Path(__file__).resolve().parent.parent / "datasets" / "holdout.jsonl"


def _load_holdout() -> list[dict[str, Any]]:
    if not HOLDOUT_PATH.exists():
        return []
    return [json.loads(line) for line in HOLDOUT_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


# Injection levels to test. Implemented via monkey-patching knowledge_loader.
LEVELS = ["bare", "global", "category", "all"]


def _patch_loaders(level: str):
    """Return a list of patches that override knowledge loader methods to simulate
    the given injection level."""
    from card_pack_agent.memory import knowledge_loader

    patches = []
    if level == "bare":
        patches += [
            patch.object(knowledge_loader.KnowledgeLoader, "taxonomy", return_value=""),
            patch.object(knowledge_loader.KnowledgeLoader, "global_style_guide", return_value=""),
            patch.object(knowledge_loader.KnowledgeLoader, "global_anti_patterns", return_value=""),
            patch.object(knowledge_loader.KnowledgeLoader, "for_category", return_value=""),
            patch.object(knowledge_loader.KnowledgeLoader, "recent_experiences_summary", return_value=""),
        ]
    elif level == "global":
        # Keep global, suppress category + experience
        patches += [
            patch.object(knowledge_loader.KnowledgeLoader, "for_category", return_value=""),
            patch.object(knowledge_loader.KnowledgeLoader, "recent_experiences_summary", return_value=""),
        ]
    elif level == "category":
        # Keep global + category, suppress experience
        patches += [
            patch.object(knowledge_loader.KnowledgeLoader, "recent_experiences_summary", return_value=""),
        ]
    # "all" — no patches
    return patches


def _eval_at_level(samples: list[dict[str, Any]], level: str) -> dict[str, float]:
    patches = _patch_loaders(level)
    for p in patches:
        p.start()
    try:
        overall_scores: list[float] = []
        pass_count = 0
        for s in samples:
            try:
                result = orchestrate(
                    TopicInput(raw_topic=s["topic"]),
                    hint_l1=s.get("gold_l1"),
                    hint_l2=s.get("gold_l2"),
                    generate_images=False,
                    persist=False,
                )
            except Exception:
                continue
            if not result.pack or not result.evaluator_report:
                continue
            js = result.evaluator_report.judge_scores or {}
            if "overall_score" in js:
                overall_scores.append(js["overall_score"])
            if result.evaluator_report.passed:
                pass_count += 1
        return {
            "avg_overall_score": sum(overall_scores) / len(overall_scores) if overall_scores else 0.0,
            "pass_rate": pass_count / max(len(samples), 1),
        }
    finally:
        for p in patches:
            p.stop()


def run(limit: int | None = None) -> dict[str, Any]:
    samples = _load_holdout()
    if limit:
        samples = samples[:limit]

    by_level: dict[str, dict[str, float]] = {}
    for level in LEVELS:
        by_level[level] = _eval_at_level(samples, level)

    # Improvement: (all - bare) / bare
    baseline = by_level["bare"]["avg_overall_score"]
    full = by_level["all"]["avg_overall_score"]
    improvement = (full - baseline) / baseline if baseline > 0 else 0.0

    # Detect monotonic regression between levels
    monotonic = (
        by_level["bare"]["avg_overall_score"]
        <= by_level["global"]["avg_overall_score"]
        <= by_level["category"]["avg_overall_score"]
        <= by_level["all"]["avg_overall_score"]
    )

    metrics = {
        "sample_size": len(samples),
        "by_level": by_level,
        "improvement_over_baseline": improvement,
        "monotonic": monotonic,
    }
    return {
        "suite": "inject",
        "metrics": metrics,
        "summary": (
            f"bare→all: {baseline:.2f}→{full:.2f} "
            f"(+{improvement:.1%}, monotonic={monotonic})"
        ),
    }
