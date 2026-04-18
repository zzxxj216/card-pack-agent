"""CLI: bench multiple image providers on a set of festival-category prompts.

Usage:
    # Mock run (no API key needed) — verify the flow
    python scripts/bench_image_providers.py --providers mock --n 3

    # Real bench across three providers
    python scripts/bench_image_providers.py \\
        --providers flux_pro,flux_schnell,openai_image \\
        --n 10 \\
        --category festival

    # Skip vision judge (just generate, cheap)
    python scripts/bench_image_providers.py --providers mock --n 5 --no-judge

Outputs:
    data/bench_runs/<timestamp>/
      ├── results.jsonl
      ├── summary.json
      └── summary.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from card_pack_agent.logging import configure_logging  # noqa: E402
from card_pack_agent.tools.image.bench import BenchCase, run_bench  # noqa: E402


# --- Bench prompt set ---
# Keep this list growing over time; it's the "holdout" for image provider decisions.

FESTIVAL_BENCH_CASES: list[BenchCase] = [
    BenchCase(
        prompt_id="festival_warm_teacup",
        prompt=(
            "A single warm cup of tea on an old wooden windowsill, "
            "soft morning light, film photography, 35mm, warm tones (#F5A623, #E8824A), "
            "shallow depth of field, large negative space above for text overlay, "
            "9:16 vertical composition"
        ),
        aspect_ratio="9:16",
        style_anchor="film photography, 35mm, natural light",
        palette=["#F5A623", "#E8824A", "#FFF8E7"],
        composition_note="subject lower-third, ample top negative space",
        tags={"l1": "festival", "l2": "resonance_healing"},
    ),
    BenchCase(
        prompt_id="festival_regret_empty_chair",
        prompt=(
            "An empty wooden chair at a dinner table, a bowl of food cooling, "
            "dusk light through a window, muted warm palette, film photography, "
            "shallow depth of field, subject centered-right, vertical 9:16"
        ),
        aspect_ratio="9:16",
        style_anchor="film photography, dusk, muted warm",
        palette=["#D4A574", "#8B6F47", "#F2E8D5"],
        composition_note="leave left third negative for overlay text",
        tags={"l1": "festival", "l2": "regret_sting"},
    ),
    BenchCase(
        prompt_id="festival_lanterns_dusk",
        prompt=(
            "Paper lanterns against dusk sky, warm red and gold, out of focus background, "
            "foreground lanterns sharp, film photography, 9:16 vertical"
        ),
        aspect_ratio="9:16",
        style_anchor="film photography, dusk",
        palette=["#C8323F", "#F5A623"],
        composition_note="lanterns fill lower third, sky negative space above",
        tags={"l1": "festival", "l2": "blessing_ritual"},
    ),
    BenchCase(
        prompt_id="festival_moon_cake_flatlay",
        prompt=(
            "Mooncake gift box flatlay, arranged on linen cloth, warm natural light, "
            "9:16 composition with headline space at top, minimalist editorial style"
        ),
        aspect_ratio="9:16",
        style_anchor="editorial flatlay, natural light",
        palette=["#C8323F", "#F5A623", "#FFFFFF"],
        composition_note="top 30% clear for headline overlay",
        tags={"l1": "festival", "l2": "utility_share"},
    ),
    BenchCase(
        prompt_id="festival_train_window",
        prompt=(
            "Train window view of blurred night scenery, reflection of a face in glass, "
            "low saturation, film grain, 35mm, 9:16, warm interior lamp glow"
        ),
        aspect_ratio="9:16",
        style_anchor="film photography, 35mm, low-light",
        palette=["#C8323F", "#F5A623", "#2C2C2A"],
        composition_note="face reflection middle-right, large negative space upper-left",
        tags={"l1": "festival", "l2": "resonance_healing"},
    ),
    BenchCase(
        prompt_id="festival_phone_unsent_message",
        prompt=(
            "Close-up of a phone screen showing a text message being typed but not sent, "
            "warm ambient light from bedside lamp, 9:16, shallow DOF, film photography"
        ),
        aspect_ratio="9:16",
        style_anchor="film photography, intimate close-up",
        palette=["#F5A623", "#2C2C2A"],
        composition_note="phone screen occupies center, ambient bokeh around",
        tags={"l1": "festival", "l2": "contrast_twist"},
    ),
    BenchCase(
        prompt_id="festival_chalk_blackboard",
        prompt=(
            "Close-up of chalk on a green blackboard, final line still being written, "
            "dust particles in beam of late afternoon light, 9:16, warm tint"
        ),
        aspect_ratio="9:16",
        style_anchor="documentary close-up, warm afternoon light",
        palette=["#D4A574", "#F2E8D5"],
        composition_note="chalk/hand on right, large blackboard negative space on left",
        tags={"l1": "festival", "l2": "resonance_healing"},
    ),
    BenchCase(
        prompt_id="festival_single_candle",
        prompt=(
            "A single lit candle on a small convenience-store cake in its plastic package, "
            "dim room, warm glow, film photography, 9:16"
        ),
        aspect_ratio="9:16",
        style_anchor="film photography, low-light, warm",
        palette=["#F5A623", "#FFF8E7"],
        composition_note="candle centered lower-third, dark negative space above",
        tags={"l1": "festival", "l2": "contrast_twist"},
    ),
    BenchCase(
        prompt_id="festival_old_photograph",
        prompt=(
            "A worn photograph in a simple wooden frame on a windowsill, "
            "sun-faded edges, soft afternoon light, 9:16, film photography"
        ),
        aspect_ratio="9:16",
        style_anchor="film photography, faded, warm afternoon",
        palette=["#B4B2A9", "#5F5E5A"],
        composition_note="frame centered-lower, soft negative space above",
        tags={"l1": "festival", "l2": "regret_sting"},
    ),
    BenchCase(
        prompt_id="festival_empty_theater_seat",
        prompt=(
            "An empty theater seat next to an occupied one, dim cinema lighting, "
            "slight motion blur on screen glow, 9:16 vertical composition"
        ),
        aspect_ratio="9:16",
        style_anchor="cinematic, dim ambient",
        palette=["#D4537E", "#2C2C2A"],
        composition_note="seats lower two-thirds, screen glow as light source",
        tags={"l1": "festival", "l2": "conflict_tension"},
    ),
]


@click.command()
@click.option(
    "--providers",
    required=True,
    help="Comma-separated providers (e.g. mock,flux_pro,openai_image)",
)
@click.option("--n", type=int, default=None,
              help="Number of bench cases (default: all)")
@click.option("--category", type=str, default="festival",
              help="Category to filter cases (currently only festival)")
@click.option("--judge/--no-judge", default=True,
              help="Run vision judge (requires Anthropic API key in non-mock mode)")
@click.option("--output", type=click.Path(), default=None,
              help="Output directory (default: data/bench_runs/<timestamp>)")
def main(providers: str, n: int | None, category: str,
         judge: bool, output: str | None) -> None:
    configure_logging()

    provider_list = [p.strip() for p in providers.split(",") if p.strip()]
    if not provider_list:
        click.echo("provide at least one provider")
        sys.exit(1)

    # Filter cases by category
    cases = [c for c in FESTIVAL_BENCH_CASES if c.tags.get("l1") == category]
    if n:
        cases = cases[:n]

    if not cases:
        click.echo(f"no cases for category {category}")
        sys.exit(1)

    click.echo(f"bench: {len(cases)} cases × {len(provider_list)} providers "
               f"= {len(cases) * len(provider_list)} generations")

    out_dir = Path(output) if output else None
    results, summaries = run_bench(
        cases=cases,
        providers=provider_list,
        output_dir=out_dir,
        with_judge=judge,
    )

    click.echo("\n=== Summary ===")
    for s in sorted(summaries, key=lambda x: x.avg_overall, reverse=True):
        click.echo(
            f"  {s.provider:20s} overall={s.avg_overall:.2f} "
            f"ok={s.n_ok}/{s.n_total} cost=${s.total_cost_usd:.3f} "
            f"latency={s.avg_latency_ms:.0f}ms"
        )
    click.echo(f"\nresults: {len(results)} rows")
    click.echo("see data/bench_runs/... for full report")


if __name__ == "__main__":
    main()
