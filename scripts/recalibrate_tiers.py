"""重算 tier 阈值。基于历史 score 分布的 P30/P60/P90。

每 50 个新样本跑一次，输出建议新阈值，**人工确认后**手动更新
`knowledge/metrics_calibration.md`。

Usage:
    python scripts/recalibrate_tiers.py
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from card_pack_agent.config import settings  # noqa: E402


def compute_score(metrics: dict) -> float:
    """Same formula as knowledge/metrics_calibration.md §综合评分公式."""
    # Simple linear weighting; z-score normalization should be done over
    # the full population — we approximate here.
    return (
        0.35 * metrics.get("completion_rate", 0)
        + 0.20 * metrics.get("share_rate", 0)
        + 0.15 * metrics.get("save_rate", 0)
        + 0.15 * metrics.get("like_rate", 0)
        + 0.10 * metrics.get("comment_rate", 0)
        + 0.05 * min(metrics.get("views", 0) / 100_000, 1.0)  # log-ish cap
    )


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def main() -> None:
    if settings.is_mock:
        print("[mock mode] no real data to recalibrate. Run with APP_MODE=dev.")
        return

    import psycopg

    with psycopg.connect(settings.postgres_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            select metrics from cases
            where metrics is not null and is_synthetic = false
            order by created_at desc
            limit 500
            """
        )
        rows = cur.fetchall()

    if len(rows) < 30:
        print(f"only {len(rows)} real samples — need at least 30 to recalibrate")
        return

    scores = sorted(compute_score(r[0]) for r in rows)
    print(f"sample size: {len(scores)}")
    print(f"  mean:   {statistics.mean(scores):.4f}")
    print(f"  median: {statistics.median(scores):.4f}")
    print(f"  stdev:  {statistics.stdev(scores):.4f}")

    print("\nsuggested thresholds:")
    print(f"  viral (P90): {percentile(scores, 0.90):.4f}")
    print(f"  good  (P60): {percentile(scores, 0.60):.4f}")
    print(f"  mid   (P30): {percentile(scores, 0.30):.4f}")

    print("\nnext steps:")
    print("  1. review the numbers above")
    print("  2. update knowledge/metrics_calibration.md §当前阈值")
    print("  3. insert a row into tier_calibrations table for audit trail")


if __name__ == "__main__":
    main()
