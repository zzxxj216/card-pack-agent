"""图像模型 bench — 多 provider 对比评测。

典型用法（CLI 见 scripts/bench_image_providers.py）：

    python scripts/bench_image_providers.py \
        --providers flux_pro,openai_image,flux_schnell \
        --category festival \
        --n 10

流程：
  1. 从测试集里取 N 个 prompt（或传入 prompt 列表）
  2. 对每个 prompt × 每个 provider 生图（并发）
  3. 对每张图跑 vision_judge
  4. 聚合：每 provider 的 mean/median 分数、成本、延迟、失败率
  5. 输出结构化报告 + markdown 摘要

输出：data/bench_runs/<timestamp>/
  - results.jsonl    （每行一条 result: prompt_id × provider × scores）
  - summary.json     （每 provider 的聚合指标）
  - summary.md       （人类可读摘要）
  - images/          （所有产出图）
"""
from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog

from .base import GenerationParams, ImageResult, ProviderName
from .generate import generate_compare
from .vision_judge import JudgeInput, VisionScore, judge_image

log = structlog.get_logger()


@dataclass
class BenchCase:
    """A single test prompt for the bench."""

    prompt_id: str
    prompt: str
    negative_prompt: str = "text, watermark, logo, typography"
    aspect_ratio: str = "9:16"
    style_anchor: str = ""
    palette: list[str] = field(default_factory=list)
    composition_note: str = ""
    tags: dict[str, str] = field(default_factory=dict)  # e.g. {"category": "festival", "l2": "resonance_healing"}


@dataclass
class BenchRunResult:
    prompt_id: str
    provider: str
    model: str
    image_url: str
    cost_usd: float
    latency_ms: int
    scores: VisionScore | None
    error: str | None = None


@dataclass
class BenchSummary:
    provider: str
    model: str
    n_total: int
    n_ok: int
    n_failed: int
    avg_overall: float
    median_overall: float
    avg_prompt_alignment: float
    avg_visual_quality: float
    avg_style_match: float
    avg_composition: float
    total_cost_usd: float
    avg_latency_ms: float
    common_issues: list[tuple[str, int]]  # [(issue_text, count)]


def run_bench(
    cases: list[BenchCase],
    providers: list[ProviderName | str],
    output_dir: Path | None = None,
    with_judge: bool = True,
) -> tuple[list[BenchRunResult], list[BenchSummary]]:
    """Run bench: every case × every provider, score each, aggregate."""
    out = output_dir or Path("./data/bench_runs") / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    results: list[BenchRunResult] = []
    results_file = out / "results.jsonl"
    log.info("bench.start",
             n_cases=len(cases),
             providers=[_provider_str(p) for p in providers],
             output_dir=str(out))

    with results_file.open("w", encoding="utf-8") as f:
        for case in cases:
            params = GenerationParams(
                prompt=case.prompt,
                negative_prompt=case.negative_prompt,
                aspect_ratio=case.aspect_ratio,
            )
            provider_results = generate_compare(params, providers, use_cache=True)

            for p_str, image_res in provider_results.items():
                scores = None
                if with_judge and image_res.ok:
                    scores = judge_image(JudgeInput(
                        image_result=image_res,
                        expected_prompt=case.prompt,
                        style_anchor=case.style_anchor,
                        palette=case.palette,
                        composition_note=case.composition_note,
                    ))

                br = BenchRunResult(
                    prompt_id=case.prompt_id,
                    provider=p_str,
                    model=image_res.model,
                    image_url=image_res.image_url,
                    cost_usd=image_res.cost_usd,
                    latency_ms=image_res.latency_ms,
                    scores=scores,
                    error=image_res.error,
                )
                results.append(br)
                f.write(json.dumps(_serialize(br), ensure_ascii=False) + "\n")

    summaries = _aggregate(results, providers)

    (out / "summary.json").write_text(
        json.dumps([asdict(s) for s in summaries], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "summary.md").write_text(_render_markdown(summaries), encoding="utf-8")

    log.info("bench.done", output_dir=str(out))
    return results, summaries


def _provider_str(p) -> str:
    return p.value if isinstance(p, ProviderName) else str(p)


def _serialize(br: BenchRunResult) -> dict:
    d = asdict(br)
    if br.scores:
        d["scores"] = br.scores.model_dump()
    return d


def _aggregate(
    results: list[BenchRunResult],
    providers: list[ProviderName | str],
) -> list[BenchSummary]:
    summaries: list[BenchSummary] = []

    for p in providers:
        p_str = _provider_str(p)
        bucket = [r for r in results if r.provider == p_str]
        if not bucket:
            continue

        ok = [r for r in bucket if r.error is None and r.scores is not None]
        n_ok = len(ok)

        overall_scores = [r.scores.overall for r in ok if r.scores]
        align_scores = [r.scores.prompt_alignment for r in ok if r.scores]
        quality_scores = [r.scores.visual_quality for r in ok if r.scores]
        style_scores = [r.scores.style_match for r in ok if r.scores]
        comp_scores = [r.scores.composition for r in ok if r.scores]

        # Count common issues
        issue_counter: dict[str, int] = {}
        for r in ok:
            if r.scores:
                for issue in r.scores.issues:
                    issue_counter[issue] = issue_counter.get(issue, 0) + 1
        common_issues = sorted(
            issue_counter.items(), key=lambda x: x[1], reverse=True,
        )[:10]

        summaries.append(BenchSummary(
            provider=p_str,
            model=bucket[0].model if bucket else "",
            n_total=len(bucket),
            n_ok=n_ok,
            n_failed=len(bucket) - n_ok,
            avg_overall=_mean(overall_scores),
            median_overall=_median(overall_scores),
            avg_prompt_alignment=_mean(align_scores),
            avg_visual_quality=_mean(quality_scores),
            avg_style_match=_mean(style_scores),
            avg_composition=_mean(comp_scores),
            total_cost_usd=round(sum(r.cost_usd for r in bucket), 4),
            avg_latency_ms=_mean([r.latency_ms for r in bucket]),
            common_issues=common_issues,
        ))

    return summaries


def _mean(xs) -> float:
    return round(statistics.fmean(xs), 3) if xs else 0.0


def _median(xs) -> float:
    return round(statistics.median(xs), 3) if xs else 0.0


def _render_markdown(summaries: list[BenchSummary]) -> str:
    lines = ["# Image Provider Bench\n"]
    lines.append(f"**Timestamp**: {datetime.now(UTC).isoformat()}\n")

    # Main comparison table
    lines.append("## Score comparison\n")
    lines.append("| Provider | Model | N ok | Overall | Align | Quality | Style | Comp | Cost $ | Latency ms |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in sorted(summaries, key=lambda x: x.avg_overall, reverse=True):
        lines.append(
            f"| `{s.provider}` | `{s.model}` | {s.n_ok}/{s.n_total} "
            f"| **{s.avg_overall:.2f}** | {s.avg_prompt_alignment:.2f} "
            f"| {s.avg_visual_quality:.2f} | {s.avg_style_match:.2f} "
            f"| {s.avg_composition:.2f} | {s.total_cost_usd:.3f} "
            f"| {s.avg_latency_ms:.0f} |"
        )

    # Cost per quality point
    lines.append("\n## Cost efficiency (cost per overall score point)\n")
    for s in sorted(
        summaries,
        key=lambda x: (x.total_cost_usd / max(x.avg_overall, 0.01)),
    ):
        if s.avg_overall > 0:
            ratio = s.total_cost_usd / (s.n_ok * s.avg_overall)
            lines.append(f"- `{s.provider}`: ${ratio:.4f} / (image × score point)")

    # Common issues per provider
    lines.append("\n## Common issues\n")
    for s in summaries:
        if not s.common_issues:
            continue
        lines.append(f"\n### {s.provider}\n")
        for issue, count in s.common_issues:
            lines.append(f"- ({count}×) {issue}")

    return "\n".join(lines)
