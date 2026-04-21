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


def rejected_pack_ids() -> set[str]:
    """Pack ids whose LATEST pack-level event is pack_reject."""
    events = load_all()  # already sorted newest first
    seen: set[str] = set()
    rejected: set[str] = set()
    for e in events:
        if not e.get("event", "").startswith("pack_"):
            continue
        pid = e.get("pack_id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        if e["event"] == "pack_reject":
            rejected.add(pid)
    return rejected


def card_reject_penalties() -> dict[str, float]:
    """Pack id → retrieval score multiplier (0.3-1.0) based on how many cards
    were human-rejected. More rejects → lower multiplier."""
    events = load_all()
    latest_by_card: dict[tuple[str, int], dict] = {}
    for e in events:
        if not e.get("event", "").startswith("card_"):
            continue
        pos = e.get("position")
        pid = e.get("pack_id")
        if pid is None or pos is None:
            continue
        k = (pid, pos)
        if k not in latest_by_card:  # load_all is newest-first, so first wins
            latest_by_card[k] = e
    rejects_per_pack: dict[str, int] = {}
    for (pid, _), e in latest_by_card.items():
        if e.get("event") == "card_reject":
            rejects_per_pack[pid] = rejects_per_pack.get(pid, 0) + 1
    return {
        pid: max(0.3, 1.0 - n / 50.0)
        for pid, n in rejects_per_pack.items()
    }


def rejection_reasons_for_packs(
    pack_ids: list[str],
    limit: int = 10,
) -> list[dict]:
    """Reject events (pack + card) with non-empty reasons, for the given packs.
    Newest first."""
    wanted = {str(p) for p in pack_ids}
    out = [
        e for e in load_all()
        if e.get("pack_id") in wanted
        and e.get("event") in ("pack_reject", "card_reject")
        and e.get("reason")
    ]
    return out[:limit]


def recent_avoid_hints(
    pack_ids: list[str] | None = None,
    limit: int = 8,
    include_card_rejects: bool = True,
) -> list[str]:
    """Return a deduped list of rejection reasons (newest first), optionally
    scoped to a specific list of pack_ids. Each string is bare reason text,
    trimmed to 160 chars, with a [pack reject] / [card reject #N] prefix."""
    wanted = {str(p) for p in pack_ids} if pack_ids else None
    seen_reasons: set[str] = set()
    out: list[str] = []
    for e in load_all():
        event = e.get("event", "")
        if not event.startswith("pack_") and not (include_card_rejects and event.startswith("card_")):
            continue
        if event not in ("pack_reject", "card_reject"):
            continue
        if wanted is not None and e.get("pack_id") not in wanted:
            continue
        reason = (e.get("reason") or "").strip()
        if not reason:
            continue
        key = reason.lower()
        if key in seen_reasons:
            continue
        seen_reasons.add(key)
        tag = "pack reject" if event == "pack_reject" else f"card reject #{e.get('position')}"
        out.append(f"[{tag}] {reason[:160]}")
        if len(out) >= limit:
            break
    return out


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
