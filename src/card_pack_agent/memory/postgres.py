"""Postgres 持久化层。存 CaseRecord。

Mock mode 使用内存 dict 替代，方便本地跑通。
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog

from ..config import settings
from ..schemas import CardPrompt, CaseRecord, L1, L2, Metrics, Script, StrategyDoc, Tier

log = structlog.get_logger()

_SELECT_COLS = (
    "pack_id, topic, topic_l1, topic_l2, topic_l3, strategy_doc, cards, "
    "script, metrics, tier, extracted_patterns, is_exploration, is_synthetic, created_at"
)


class CaseStore:
    """CaseRecord CRUD。"""

    def __init__(self) -> None:
        self._memory: dict[UUID, CaseRecord] = {}

    def _connect(self) -> Any:
        """Lazy psycopg3 connection. Mock mode never calls this."""
        settings.require_real_mode("CaseStore")
        import psycopg
        return psycopg.connect(settings.postgres_dsn, autocommit=True)

    # --- Write ---

    def insert(self, case: CaseRecord) -> None:
        if settings.is_mock:
            self._memory[case.pack_id] = case
            log.info("case_store.insert.mock", pack_id=str(case.pack_id))
            return

        try:
            self._do_insert(case)
        except Exception as exc:
            self._memory[case.pack_id] = case
            log.warning("case_store.insert.fallback_memory",
                        pack_id=str(case.pack_id), error=str(exc)[:200])

    def _do_insert(self, case: CaseRecord) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into cases (
                  pack_id, topic, topic_l1, topic_l2, topic_l3,
                  strategy_doc, cards, script, metrics, tier,
                  extracted_patterns, is_exploration, is_synthetic, created_at
                ) values (
                  %(pack_id)s, %(topic)s, %(topic_l1)s, %(topic_l2)s, %(topic_l3)s,
                  %(strategy_doc)s::jsonb, %(cards)s::jsonb, %(script)s::jsonb,
                  %(metrics)s::jsonb, %(tier)s,
                  %(extracted_patterns)s::jsonb, %(is_exploration)s, %(is_synthetic)s, %(created_at)s
                )
                on conflict (pack_id) do update set
                  metrics = excluded.metrics,
                  tier = excluded.tier,
                  extracted_patterns = excluded.extracted_patterns
                """,
                {
                    "pack_id": str(case.pack_id),
                    "topic": case.topic,
                    "topic_l1": case.topic_l1.value,
                    "topic_l2": case.topic_l2.value,
                    "topic_l3": case.topic_l3,
                    "strategy_doc": case.strategy_doc.model_dump_json(),
                    "cards": _dump_list(case.cards),
                    "script": case.script.model_dump_json(),
                    "metrics": case.metrics.model_dump_json() if case.metrics else None,
                    "tier": case.tier.value if case.tier else None,
                    "extracted_patterns": _dump_json(case.extracted_patterns),
                    "is_exploration": case.is_exploration,
                    "is_synthetic": case.is_synthetic,
                    "created_at": case.created_at,
                },
            )
        log.info("case_store.insert", pack_id=str(case.pack_id))

    def update_metrics(self, pack_id: UUID, metrics: dict[str, Any], tier: Tier) -> None:
        if settings.is_mock:
            case = self._memory.get(pack_id)
            if case:
                case.metrics = Metrics.model_validate(metrics)
                case.tier = tier
            return
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update cases set metrics = %s::jsonb, tier = %s where pack_id = %s",
                (metrics, tier.value, str(pack_id)),
            )

    # --- Read ---

    def get(self, pack_id: UUID) -> CaseRecord | None:
        if settings.is_mock:
            return self._memory.get(pack_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"select {_SELECT_COLS} from cases where pack_id = %s",
                (str(pack_id),),
            )
            row = cur.fetchone()
        return _row_to_case(row) if row else None

    def list_by_category(
        self,
        l1: L1,
        l2: L2 | None = None,
        tier_gte: Tier | None = None,
        limit: int = 20,
    ) -> list[CaseRecord]:
        if settings.is_mock:
            rows = [
                c for c in self._memory.values()
                if c.topic_l1 == l1
                and (l2 is None or c.topic_l2 == l2)
                and (tier_gte is None or _tier_rank(c.tier) >= _tier_rank(tier_gte))
            ]
            return rows[:limit]

        sql = f"select {_SELECT_COLS} from cases where topic_l1 = %s"
        params: list[Any] = [l1.value]
        if l2 is not None:
            sql += " and topic_l2 = %s"
            params.append(l2.value)
        if tier_gte is not None:
            threshold = _tier_rank(tier_gte)
            tiers_ok = [t.value for t in Tier if _tier_rank(t) >= threshold]
            sql += " and tier = ANY(%s)"
            params.append(tiers_ok)
        sql += " order by created_at desc limit %s"
        params.append(limit)

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [_row_to_case(r) for r in rows]


def _dump_json(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def _dump_list(items: list[Any]) -> str:
    return json.dumps([i.model_dump() if hasattr(i, "model_dump") else i for i in items],
                      default=str, ensure_ascii=False)


def _jsonb(val: Any) -> Any:
    """psycopg returns jsonb columns as already-decoded Python objects in some
    versions and as strings in others. Normalize to Python objects."""
    if isinstance(val, (dict, list)) or val is None:
        return val
    if isinstance(val, (bytes, bytearray)):
        val = val.decode("utf-8")
    if isinstance(val, str):
        return json.loads(val)
    return val


def _row_to_case(row: tuple) -> CaseRecord:
    (
        pack_id, topic, topic_l1, topic_l2, topic_l3,
        strategy_doc, cards, script, metrics, tier,
        extracted_patterns, is_exploration, is_synthetic, created_at,
    ) = row
    return CaseRecord(
        pack_id=pack_id if isinstance(pack_id, UUID) else UUID(str(pack_id)),
        topic=topic,
        topic_l1=L1(topic_l1),
        topic_l2=L2(topic_l2),
        topic_l3=list(topic_l3 or []),
        strategy_doc=StrategyDoc.model_validate(_jsonb(strategy_doc)),
        cards=[CardPrompt.model_validate(c) for c in (_jsonb(cards) or [])],
        script=Script.model_validate(_jsonb(script)),
        metrics=Metrics.model_validate(_jsonb(metrics)) if metrics is not None else None,
        tier=Tier(tier) if tier else None,
        extracted_patterns=_jsonb(extracted_patterns) or [],
        is_exploration=bool(is_exploration),
        is_synthetic=bool(is_synthetic),
        created_at=created_at,
    )


def _tier_rank(tier: Tier | None) -> int:
    order = {Tier.BAD: 0, Tier.MID: 1, Tier.GOOD: 2, Tier.VIRAL: 3}
    return order.get(tier, -1) if tier else -1


# Module-level singleton
case_store = CaseStore()
