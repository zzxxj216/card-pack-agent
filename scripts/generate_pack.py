"""CLI: 生成一个完整卡贴包。

Usage:
    python scripts/generate_pack.py --topic "中秋节" --category festival
    python scripts/generate_pack.py --topic "母亲节" --category festival --mechanism regret_sting
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from card_pack_agent.logging import configure_logging  # noqa: E402
from card_pack_agent.orchestrator import run  # noqa: E402
from card_pack_agent.schemas import TopicInput  # noqa: E402


@click.command()
@click.option("--topic", required=True)
@click.option("--category", default=None, help="L1 hint (e.g. festival)")
@click.option("--mechanism", default=None, help="L2 hint (e.g. resonance_healing)")
@click.option("--images/--no-images", default=False)
@click.option("--output", default=None, type=click.Path(), help="Save pack JSON to file")
def main(topic: str, category: str | None, mechanism: str | None,
         images: bool, output: str | None) -> None:
    configure_logging()
    result = run(
        TopicInput(raw_topic=topic),
        hint_l1=category,
        hint_l2=mechanism,
        generate_images=images,
    )

    if result.clarification:
        click.echo("[!] clarification needed:")
        for q in result.clarification.questions:
            click.echo(f"   - {q}")
        sys.exit(2)

    if not result.ok:
        click.echo(f"[FAIL] verdict={result.evaluator_report.verdict.value}")
        for issue in result.evaluator_report.issues:
            click.echo(f"  [{issue.severity.value}] {issue.code}: {issue.message}")
        sys.exit(1)

    pack = result.pack
    report = result.evaluator_report
    click.echo(f"[OK] pack_id={pack.pack_id}")
    click.echo(f"  class: {pack.strategy.classification.l1} / {pack.strategy.classification.l2}")
    click.echo(f"  cards={len(pack.cards)} shots={len(pack.script.shots)} duration={pack.script.total_duration_s}s")
    click.echo(f"  evaluator: {report.verdict.value}")
    if report.judge_scores:
        click.echo(f"  judge: {json.dumps(report.judge_scores, ensure_ascii=False)}")

    if output:
        Path(output).write_text(pack.model_dump_json(indent=2), encoding="utf-8")
        click.echo(f"  saved: {output}")


if __name__ == "__main__":
    main()
