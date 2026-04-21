"""Orchestrator — 主编排器。

流程：TopicInput → Planner → Generator (cards + script) → Evaluator → (images) → persist

每次 run 收集所有 CallMeta 并汇总 token/cost，返回给调用方，方便成本追踪。

副产物：所有成功到达 Pack 阶段的运行（无论 verdict）都会写一份 artifact 到
`ARTIFACTS_DIR/{pack_id}.json`，前端评测页从那里读。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import structlog

from .agents import generator, planner
from .memory.postgres import case_store
from .schemas import (
    CaseRecord,
    ClarificationRequest,
    EvaluatorReport,
    L1,
    L2,
    Pack,
    StrategyDoc,
    TopicInput,
)
from .structured_output import CallMeta, StructuredCallError
from .tools import evaluator, image_gen

ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ROOT / "artifacts" / "packs"

log = structlog.get_logger()


@dataclass
class CostSummary:
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    per_role: dict[str, dict] = field(default_factory=dict)

    def add(self, meta: CallMeta) -> None:
        self.total_input_tokens += meta.input_tokens
        self.total_output_tokens += meta.output_tokens
        self.total_cost_usd += meta.estimated_cost_usd
        role = meta.role or "unknown"
        bucket = self.per_role.setdefault(role, {
            "calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
        })
        bucket["calls"] += 1
        bucket["input_tokens"] += meta.input_tokens
        bucket["output_tokens"] += meta.output_tokens
        bucket["cost_usd"] += meta.estimated_cost_usd

    def as_dict(self) -> dict:
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "per_role": {
                r: {**b, "cost_usd": round(b["cost_usd"], 6)}
                for r, b in self.per_role.items()
            },
        }


class OrchestratorResult:
    def __init__(
        self,
        pack: Pack | None,
        clarification: ClarificationRequest | None,
        evaluator_report: EvaluatorReport | None,
        cost: CostSummary,
        fatal_error: str | None = None,
    ) -> None:
        self.pack = pack
        self.clarification = clarification
        self.evaluator_report = evaluator_report
        self.cost = cost
        self.fatal_error = fatal_error

    @property
    def ok(self) -> bool:
        return (
            self.fatal_error is None
            and self.pack is not None
            and (self.evaluator_report is None or self.evaluator_report.passed)
        )


def run(
    topic_input: TopicInput,
    *,
    hint_l1: str | None = None,
    hint_l2: str | None = None,
    generate_images: bool = False,
    persist: bool = True,
    max_regenerate_on_fail: int = 1,
) -> OrchestratorResult:
    """End-to-end 生成流程。"""
    cost = CostSummary()

    # 1) Planner
    try:
        plan_result, plan_meta = planner.plan(
            topic_input, hint_l1=hint_l1, hint_l2=hint_l2,
        )
        cost.add(plan_meta)
    except StructuredCallError as e:
        log.error("orchestrator.planner_failed", error=str(e))
        cost.add(e.meta)
        return OrchestratorResult(
            pack=None, clarification=None, evaluator_report=None,
            cost=cost, fatal_error=f"planner exhausted: {e}",
        )

    if isinstance(plan_result, ClarificationRequest):
        log.info("orchestrator.clarification_needed")
        return OrchestratorResult(
            pack=None, clarification=plan_result, evaluator_report=None,
            cost=cost,
        )

    strategy: StrategyDoc = plan_result

    # 2) Generator + Evaluator with regeneration loop
    pack, report = None, None
    attempts = 0
    max_attempts = max_regenerate_on_fail + 1

    while attempts < max_attempts:
        attempts += 1
        try:
            pack, report = _generate_and_evaluate(strategy, topic_input.raw_topic, cost)
        except StructuredCallError as e:
            log.error("orchestrator.generator_failed",
                      attempt=attempts, error=str(e))
            cost.add(e.meta)
            return OrchestratorResult(
                pack=None, clarification=None, evaluator_report=None,
                cost=cost, fatal_error=f"generator exhausted: {e}",
            )

        if report.passed:
            break

        log.warning("orchestrator.evaluator_fail",
                    attempt=attempts,
                    issues=[i.code for i in report.issues])
        if attempts >= max_attempts:
            break

    # 3) Images (only if passed)
    if report and report.passed and generate_images:
        image_map = image_gen.generate_batch(pack.cards)
        pack.card_image_urls = image_map

    # 4) Persist to vector/case store (only if passed)
    if persist and report and report.passed:
        _persist(pack, strategy)

    # 5) Always dump artifact to disk (pass or fail) for the eval UI.
    # Skip in mock mode — test runs shouldn't pollute artifacts/packs/.
    from .config import settings
    if pack is not None and not settings.is_mock:
        try:
            _dump_artifact(
                pack=pack,
                report=report,
                cost=cost,
                topic_input=topic_input,
                hint_l1=hint_l1,
                hint_l2=hint_l2,
            )
        except Exception as exc:
            log.warning("orchestrator.artifact_dump_failed", error=str(exc)[:200])

    log.info("orchestrator.done",
             pack_id=str(pack.pack_id) if pack else None,
             verdict=report.verdict.value if report else None,
             total_cost_usd=cost.total_cost_usd)

    return OrchestratorResult(
        pack=pack, clarification=None, evaluator_report=report, cost=cost,
    )


def _dump_artifact(
    *,
    pack: Pack,
    report: EvaluatorReport | None,
    cost: CostSummary,
    topic_input: TopicInput,
    hint_l1: str | None,
    hint_l2: str | None,
) -> Path:
    """Write pack + report + cost to artifacts/packs/{pack_id}.json."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_DIR / f"{pack.pack_id}.json"

    artifact = {
        "pack_id": str(pack.pack_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "topic": pack.topic,
        "raw_topic": topic_input.raw_topic,
        "hint_l1": hint_l1,
        "hint_l2": hint_l2,
        "pack": json.loads(pack.model_dump_json()),
        "evaluator_report": (
            json.loads(report.model_dump_json()) if report is not None else None
        ),
        "cost": cost.as_dict(),
    }
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("orchestrator.artifact_dumped", path=str(path), pack_id=str(pack.pack_id))
    return path


def load_artifact(pack_id: str | UUID) -> dict | None:
    """Read back a dumped artifact by pack_id. Returns None if not found."""
    path = ARTIFACTS_DIR / f"{pack_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_artifacts() -> list[dict]:
    """List pack artifacts sorted by created_at desc (newest first).

    Returns a lightweight summary per pack (not the full Pack body).
    """
    if not ARTIFACTS_DIR.exists():
        return []
    from . import feedback as feedback_mod
    summaries = []
    for p in ARTIFACTS_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        report = data.get("evaluator_report") or {}
        judge = report.get("judge_scores") or {}
        pack = data.get("pack") or {}
        strategy = pack.get("strategy") or {}
        clf = strategy.get("classification") or {}
        script = pack.get("script") or {}
        n_shots = len(script.get("shots") or [])
        pid = data.get("pack_id")

        fb = feedback_mod.summary_for_pack(pid) if pid else {}
        summaries.append({
            "pack_id": pid,
            "topic": data.get("topic"),
            "created_at": data.get("created_at"),
            "hint_l1": data.get("hint_l1"),
            "hint_l2": data.get("hint_l2"),
            "actual_l1": (clf.get("l1") or "").replace("L1.", "").lower() or None,
            "actual_l2": (clf.get("l2") or "").replace("L2.", "").lower() or None,
            "verdict": report.get("verdict"),
            "n_issues": len(report.get("issues") or []),
            "overall_score": judge.get("overall_score") or judge.get("overall"),
            "cost_usd": (data.get("cost") or {}).get("total_cost_usd"),
            "n_cards": len(pack.get("cards") or []),
            "n_shots": n_shots,
            "total_duration_s": script.get("total_duration_s"),
            "pack_verdict": fb.get("pack_verdict"),
            "n_card_rejects": fb.get("n_card_rejects", 0),
            "path": str(p),
        })
    summaries.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return summaries


def _generate_and_evaluate(
    strategy: StrategyDoc, topic: str, cost: CostSummary,
) -> tuple[Pack, EvaluatorReport]:
    cards, cards_meta = generator.generate_cards(strategy)
    cost.add(cards_meta)

    try:
        script, script_meta = generator.generate_script(strategy, cards)
        cost.add(script_meta)
    except Exception as exc:
        log.warning("orchestrator.script_fallback", error=str(exc)[:200])
        from .schemas import BGMSuggestion, Script, Shot
        script = Script(
            total_duration_s=40.0,
            bgm_suggestion=BGMSuggestion(
                mood="ambient calm",
                reference="lo-fi piano, soft ambient",
            ),
            shots=[
                Shot(
                    position=c.position,
                    duration_s=0.8 if c.position <= 3 else 1.5,
                )
                for c in cards
            ],
        )

    pack = Pack(
        pack_id=uuid4(),
        topic=topic,
        strategy=strategy,
        cards=cards,
        script=script,
    )
    report = evaluator.evaluate(pack, run_judge=True)
    return pack, report


def _persist(pack: Pack, strategy: StrategyDoc) -> None:
    from .memory.vector import COLLECTION_TOPIC, embed, vector_store

    l1 = _coerce_enum(strategy.classification.l1, L1)
    l2 = _coerce_enum(strategy.classification.l2, L2)
    case = CaseRecord(
        pack_id=pack.pack_id,
        topic=pack.topic,
        topic_l1=l1,
        topic_l2=l2,
        topic_l3=strategy.classification.l3,
        strategy_doc=strategy,
        cards=pack.cards,
        script=pack.script,
        metrics=None,
        tier=None,
        is_synthetic=False,
    )
    case_store.insert(case)

    try:
        vector_store.upsert(
            collection=COLLECTION_TOPIC,
            point_id=str(case.pack_id),
            vector=embed(case.topic),
            payload={
                "pack_id": str(case.pack_id),
                "topic": case.topic,
                "l1": case.topic_l1.value,
                "l2": case.topic_l2.value,
                "tier": case.tier.value if case.tier else "bad",
                "is_synthetic": False,
                "created_at": case.created_at.isoformat(),
            },
        )
    except Exception as exc:
        log.warning("persist.vector_upsert_failed", error=str(exc)[:200])


def _coerce_enum(value, enum_cls):
    if isinstance(value, enum_cls):
        return value
    return enum_cls(value)
