"""CLI 入口。注册在 pyproject.toml 的 [project.scripts]。"""
from __future__ import annotations

import click

from .logging import configure_logging


@click.group()
def main() -> None:
    """card-pack — TikTok 卡贴包生成 CLI。"""
    configure_logging()


@main.command()
@click.option("--topic", required=True, help="话题或素材")
@click.option("--category", default=None, help="L1 提示（festival / emotional / ...）")
@click.option("--mechanism", default=None, help="L2 提示（resonance_healing / ...）")
@click.option("--images/--no-images", default=False, help="是否生成图像（默认否）")
def generate(topic: str, category: str | None, mechanism: str | None, images: bool) -> None:
    """生成一个完整卡贴包。"""
    from .orchestrator import run
    from .schemas import TopicInput

    result = run(
        TopicInput(raw_topic=topic),
        hint_l1=category,
        hint_l2=mechanism,
        generate_images=images,
    )

    if result.clarification:
        click.echo("[!] 需要澄清：")
        for q in result.clarification.questions:
            click.echo(f"   - {q}")
        return

    if not result.ok:
        click.echo(f"[FAIL] {[i.code for i in result.evaluator_report.issues]}")
        for issue in result.evaluator_report.issues:
            click.echo(f"  [{issue.severity.value}] {issue.code}: {issue.message}")
        return

    pack = result.pack
    click.echo(f"[OK] pack_id={pack.pack_id}")
    click.echo(f"  classification: {pack.strategy.classification.l1} / {pack.strategy.classification.l2}")
    click.echo(f"  cards: {len(pack.cards)}, shots: {len(pack.script.shots)}")
    click.echo(f"  duration: {pack.script.total_duration_s}s")
    click.echo(f"  evaluator: {result.evaluator_report.verdict.value}")
    if result.evaluator_report.judge_scores:
        click.echo(f"  judge_overall: {result.evaluator_report.judge_scores.get('overall_score', '?')}")


@main.command()
def init_db() -> None:
    """初始化 Postgres schema + Qdrant collections。"""
    from scripts.init_db import main as init_db_main
    init_db_main()


if __name__ == "__main__":
    main()
