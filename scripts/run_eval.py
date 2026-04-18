"""Eval runner — 统一入口跑四类评测。

Usage:
    python scripts/run_eval.py --all
    python scripts/run_eval.py --suite classify
    python scripts/run_eval.py --suite generate --limit 5
    python scripts/run_eval.py --all --report eval/runs/YYYY-MM-DD.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from card_pack_agent.logging import configure_logging  # noqa: E402


SUITES = ["classify", "retrieve", "generate", "inject"]


@click.command()
@click.option("--all", "run_all", is_flag=True, help="Run all suites")
@click.option("--suite", type=click.Choice(SUITES), help="Run a single suite")
@click.option("--limit", type=int, default=None, help="Limit samples per suite")
@click.option("--report", type=click.Path(), default=None, help="JSON output path")
def main(run_all: bool, suite: str | None, limit: int | None, report: str | None) -> None:
    configure_logging()
    if not run_all and not suite:
        click.echo("specify --all or --suite")
        sys.exit(1)

    suites_to_run = SUITES if run_all else [suite]
    results: dict[str, dict] = {}

    from eval.runners import classify as r_classify
    from eval.runners import generate as r_generate
    from eval.runners import inject as r_inject
    from eval.runners import retrieve as r_retrieve

    runners = {
        "classify": r_classify.run,
        "retrieve": r_retrieve.run,
        "generate": r_generate.run,
        "inject": r_inject.run,
    }

    for s in suites_to_run:
        click.echo(f"\n=== running suite: {s} ===")
        try:
            result = runners[s](limit=limit)
            results[s] = result
            click.echo(f"  {s}: {result.get('summary', 'done')}")
        except Exception as e:
            click.echo(f"  {s}: FAILED — {e}")
            results[s] = {"error": str(e)}

    # Report
    out = {
        "timestamp": datetime.utcnow().isoformat(),
        "suites": results,
    }
    if report:
        report_path = Path(report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        click.echo(f"\nreport: {report_path}")
    else:
        click.echo(f"\nsummary:\n{json.dumps(out, ensure_ascii=False, indent=2)}")

    # Exit non-zero if any suite errored
    if any("error" in r for r in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
