"""Backfill artifacts/packs/*.json into Postgres + Qdrant.

These are packs that were generated before real-mode persistence was wired.
Imports each artifact as a CaseRecord with no metrics/tier (exploration).

Usage:
    APP_MODE=dev python scripts/backfill_artifacts.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import click  # noqa: E402

from card_pack_agent.config import settings  # noqa: E402
from card_pack_agent.logging import configure_logging  # noqa: E402
from card_pack_agent.memory.postgres import case_store  # noqa: E402
from card_pack_agent.memory.vector import COLLECTION_TOPIC, embed, vector_store  # noqa: E402
from card_pack_agent.schemas import (  # noqa: E402
    CardPrompt,
    CaseRecord,
    L1,
    L2,
    Script,
    StrategyDoc,
)


def _coerce_enum(value, cls):
    return value if isinstance(value, cls) else cls(value)


def backfill_one(artifact: dict) -> str:
    pack = artifact["pack"]
    strategy = StrategyDoc.model_validate(pack["strategy"])
    cards = [CardPrompt.model_validate(c) for c in pack["cards"]]
    script = Script.model_validate(pack["script"])

    case = CaseRecord(
        pack_id=pack["pack_id"],
        topic=pack["topic"],
        topic_l1=_coerce_enum(strategy.classification.l1, L1),
        topic_l2=_coerce_enum(strategy.classification.l2, L2),
        topic_l3=strategy.classification.l3,
        strategy_doc=strategy,
        cards=cards,
        script=script,
        metrics=None,
        tier=None,
        is_exploration=True,
        is_synthetic=False,
        created_at=_parse_created_at(artifact.get("created_at") or pack.get("created_at")),
    )
    case_store.insert(case)

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
    return str(case.pack_id)


def _parse_created_at(iso: str | None):
    from datetime import datetime
    if not iso:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return datetime.utcnow()


@click.command()
@click.option("--dir", "artifacts_dir", default=str(ROOT / "artifacts" / "packs"),
              show_default=True, help="artifact directory")
def main(artifacts_dir: str) -> None:
    if settings.is_mock:
        raise SystemExit("refusing to run in APP_MODE=mock; set APP_MODE=dev")

    configure_logging()
    adir = Path(artifacts_dir)
    files = sorted(adir.glob("*.json"))
    if not files:
        click.echo(f"no artifacts found in {adir}")
        return
    click.echo(f"backfilling {len(files)} artifact(s) from {adir}")
    ok, fail = 0, 0
    for f in files:
        try:
            with f.open(encoding="utf-8") as fh:
                artifact = json.load(fh)
            pid = backfill_one(artifact)
            click.echo(f"  ok  {f.name}  pack_id={pid}")
            ok += 1
        except Exception as exc:
            click.echo(f"  FAIL {f.name}  {type(exc).__name__}: {exc}")
            fail += 1
    click.echo(f"done: {ok} ok, {fail} failed")


if __name__ == "__main__":
    main()
