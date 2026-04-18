"""TK 指标拉取。

Phase 1-3: 人工填表格（Google Sheet / Airtable）→ 这里读 CSV
Phase 4+: 接 TK API
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from uuid import UUID

from ..schemas import Metrics


def pull_metrics_from_csv(csv_path: Path) -> dict[UUID, Metrics]:
    """从 CSV 读指标。

    期望列：
      pack_id, views, completion_rate, like_rate, share_rate, comment_rate,
      save_rate, most_memorable_positions (comma-sep), sentiment, mentions
    """
    results: dict[UUID, Metrics] = {}
    if not csv_path.exists():
        return results

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pack_id = UUID(row["pack_id"])
                mem_positions = [
                    int(x) for x in (row.get("most_memorable_positions") or "").split(",")
                    if x.strip().isdigit()
                ]
                mentions = [
                    m.strip() for m in (row.get("mentions") or "").split("|")
                    if m.strip()
                ]
                results[pack_id] = Metrics(
                    views=int(row.get("views") or 0),
                    completion_rate=float(row.get("completion_rate") or 0),
                    like_rate=float(row.get("like_rate") or 0),
                    share_rate=float(row.get("share_rate") or 0),
                    comment_rate=float(row.get("comment_rate") or 0),
                    save_rate=float(row.get("save_rate") or 0),
                    most_memorable_positions=mem_positions,
                    dominant_comment_sentiment=row.get("sentiment") or None,
                    comment_mentions=mentions,
                )
            except (ValueError, KeyError) as e:
                # skip malformed row
                import sys
                print(f"skipping row: {e}", file=sys.stderr)
                continue
    return results


def pull_from_tiktok_api(*_args, **_kwargs) -> dict[UUID, Metrics]:  # noqa: ARG001
    """Phase 4 task: real TK API integration."""
    raise NotImplementedError("TikTok API integration is a Phase 4 deliverable")
