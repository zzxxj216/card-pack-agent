"""Orchestrator — 主编排器。

流程：TopicInput → Planner → Generator (cards + script) → Evaluator → (images) → persist

每次 run 收集所有 CallMeta 并汇总 token/cost，返回给调用方，方便成本追踪。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

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

    # 4) Persist
    if persist and report and report.passed:
        _persist(pack, strategy)

    log.info("orchestrator.done",
             pack_id=str(pack.pack_id) if pack else None,
             verdict=report.verdict.value if report else None,
             total_cost_usd=cost.total_cost_usd)

    return OrchestratorResult(
        pack=pack, clarification=None, evaluator_report=report, cost=cost,
    )


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


def _coerce_enum(value, enum_cls):
    if isinstance(value, enum_cls):
        return value
    return enum_cls(value)
