"""CI gate：扫 eval runs 最新结果，对照阈值决定是否让 CI 通过。

Usage:
    python scripts/check_eval_thresholds.py eval/runs/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


# --- Thresholds (update as baselines evolve) ---
# These are *minimum acceptable* values. Regression below these fails CI.

THRESHOLDS: dict[str, dict[str, float]] = {
    "classify": {
        "l1_accuracy": 0.70,
        "l1_l2_joint_accuracy": 0.55,
    },
    "retrieve": {
        "hit_at_5_good_plus": 0.40,
    },
    "generate": {
        "avg_overall_score": 3.0,
        "evaluator_pass_rate": 0.70,
    },
    "inject": {
        "improvement_over_baseline": 0.0,  # must not regress
    },
}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_eval_thresholds.py <runs_dir>")
        return 1

    runs_dir = Path(sys.argv[1])
    if not runs_dir.is_dir():
        print(f"no runs directory: {runs_dir}")
        return 0  # treat as no-op, not a failure

    reports = sorted(runs_dir.glob("*.json"))
    if not reports:
        print("no eval reports found, skipping threshold check")
        return 0

    latest = reports[-1]
    print(f"checking {latest}...")
    data = json.loads(latest.read_text(encoding="utf-8"))

    failures: list[str] = []
    for suite, thresholds in THRESHOLDS.items():
        suite_result = data.get("suites", {}).get(suite)
        if not suite_result:
            continue
        if "error" in suite_result:
            failures.append(f"{suite}: errored")
            continue
        for metric, min_val in thresholds.items():
            actual = suite_result.get("metrics", {}).get(metric)
            if actual is None:
                # soft miss — skip rather than fail
                continue
            if actual < min_val:
                failures.append(f"{suite}.{metric}: {actual:.3f} < {min_val:.3f}")

    if failures:
        print("REGRESSION:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("all thresholds ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
