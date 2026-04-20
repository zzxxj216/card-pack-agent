"""人工反馈收集 — pack/card 级别的 reject/approve + 原因。

存储：append-only JSONL at `artifacts/feedback.jsonl`
一行一个事件，方便后续 pandas 读取做分析 / 训练反例。

事件 schema：
    {
      "ts": "2026-04-20T01:50:00Z",
      "pack_id": "...",
      "event": "pack_reject" | "pack_approve" | "card_reject" | "card_approve",
      "position": null | int,      # card_* 事件才有
      "reason": "...",
      "reviewer": "human",
      "tags": ["off_tone", "stale_meme", ...],  # 可选，前端填 or 后续分类
    }
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent.parent
FEEDBACK_PATH = ROOT / "artifacts" / "feedback.jsonl"

EventType = Literal[
    "pack_reject", "pack_approve",
    "card_reject", "card_approve",
]


def record(
    *,
    pack_id: str,
    event: EventType,
    reason: str = "",
    position: int | None = None,
    reviewer: str = "human",
    tags: list[str] | None = None,
) -> dict:
    """Append one feedback event. Returns the recorded dict."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pack_id": pack_id,
        "event": event,
        "position": position,
        "reason": reason.strip(),
        "reviewer": reviewer,
        "tags": tags or [],
    }
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_all() -> list[dict]:
    """Read all feedback events; newest first."""
    if not FEEDBACK_PATH.exists():
        return []
    out = []
    for line in FEEDBACK_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.sort(key=lambda e: e.get("ts") or "", reverse=True)
    return out


def load_for_pack(pack_id: str) -> list[dict]:
    """Events for one pack, newest first."""
    return [e for e in load_all() if e.get("pack_id") == pack_id]


def summary_for_pack(pack_id: str) -> dict:
    """Aggregate: pack-level verdict + per-card rejections."""
    events = load_for_pack(pack_id)
    pack_events = [e for e in events if e["event"].startswith("pack_")]
    card_events = [e for e in events if e["event"].startswith("card_")]

    latest_pack = pack_events[0] if pack_events else None
    # Latest event per card position
    per_card: dict[int, dict] = {}
    for e in card_events:
        pos = e.get("position")
        if pos is None:
            continue
        if pos not in per_card or (e.get("ts") or "") > (per_card[pos].get("ts") or ""):
            per_card[pos] = e

    return {
        "pack_verdict": latest_pack.get("event") if latest_pack else None,
        "pack_reason": latest_pack.get("reason") if latest_pack else None,
        "pack_ts": latest_pack.get("ts") if latest_pack else None,
        "per_card": per_card,
        "total_events": len(events),
        "n_pack_rejects": sum(1 for e in pack_events if e["event"] == "pack_reject"),
        "n_card_rejects": sum(1 for e in card_events if e["event"] == "card_reject"),
    }
