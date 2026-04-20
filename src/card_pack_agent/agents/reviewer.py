"""Reviewer Agent — 异步复盘。

不阻塞发布。每周跑一次，产出 experience_log，**由人工 review 后合入**。
"""
from __future__ import annotations

from datetime import datetime

import structlog

from ..llm import LLMRole, llm
from ..memory.knowledge_loader import knowledge
from ..schemas import CaseRecord, L1, ReviewReport, Tier

log = structlog.get_logger()


SYSTEM_TEMPLATE = """You are the Reviewer Agent (asynchronous retrospective).

Your job: from a batch of post-publish card packs and their real-world
performance metrics, attribute *why* each pack did well or poorly, and extract
reusable rules. All rules and free-text fields must be written in English.

<principles>
1. Every attribution must cite a concrete visual / copy / narrative / pacing
   lever. Reject vague conclusions like "strong resonance".
2. Each extracted rule must be usable as a Generator constraint.
3. Distinguish strong signals (>=3 packs of evidence) from weak signals.
4. Prefer specific-and-possibly-wrong over vague-and-technically-right.
5. Do not speculate about external factors (algorithm, weather, seasonality) —
   those are for human judgment.
</principles>

{category_playbook}

---

{failure_library}

---

# Output

Strict JSON only (no markdown fence, no prose). Schema:

```json
{{
  "window": {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "category": "festival"}},
  "sample_size": {{"top": 5, "bottom": 5}},
  "per_pack_attribution": [
    {{
      "pack_id": "...",
      "tier": "good",
      "best_cards": {{"positions": [3, 15, 30], "common_traits": "..."}},
      "worst_cards": {{"positions": [7, 22], "common_traits": "..."}},
      "primary_driver": "single-object hook with large negative space"
    }}
  ],
  "cross_pack_contrast": {{
    "visual": [
      {{
        "dimension": "palette",
        "top_pattern": "...",
        "bottom_pattern": "...",
        "evidence": ["pack_id1 pos 1-5", "pack_id2 pos 7-12"]
      }}
    ],
    "copy": [],
    "narrative": [],
    "pacing": []
  }},
  "extracted_rules": [
    {{
      "id": "w15-r1",
      "polarity": "positive",
      "rule": "For festival/resonance_healing, hook cards should use a single everyday object close-up with short bold overlay; avoid direct-face portraits.",
      "evidence_strength": "strong",
      "evidence_packs": ["...", "..."],
      "scope": "category:festival, mechanism:resonance_healing",
      "target_file": "knowledge/categories/festival.md"
    }}
  ],
  "open_questions": ["..."],
  "summary_for_humans": "<= 200 words English summary for the weekly human review"
}}
```
"""


USER_TEMPLATE = """# Review window

{window}

Category: {category}
Sample: top={n_top}, bottom={n_bottom}

# Top group (tier >= good)

{top_packs}

# Bottom group (tier <= mid)

{bottom_packs}

# Your task (4 steps)

1. Per-pack attribution: for each Top and each Bottom pack, identify the best
   ~5 and worst ~5 cards (by single_card_tier or comment signal) and describe
   their common visual/copy/narrative traits.
2. Cross-pack contrast: compare Top vs Bottom along visual / copy / narrative /
   pacing dimensions. Each difference must cite evidence (specific packs & cards).
3. Extract 3-8 landable rules with polarity, evidence_strength, scope, and a
   target_file for where the rule should land.
4. List open questions worth watching next window.

Emit the structured ReviewReport JSON per the schema.
"""


def review(
    top_packs: list[CaseRecord],
    bottom_packs: list[CaseRecord],
    category: L1,
    window_start: datetime,
    window_end: datetime,
) -> ReviewReport:
    log.info("reviewer.start", top=len(top_packs), bottom=len(bottom_packs))

    system = SYSTEM_TEMPLATE.format(
        category_playbook=knowledge.for_category(category.value),
        failure_library=knowledge.failure_library(),
    )
    user = USER_TEMPLATE.format(
        window=f"{window_start.date()} → {window_end.date()}",
        category=category.value,
        n_top=len(top_packs),
        n_bottom=len(bottom_packs),
        top_packs=_format_packs(top_packs),
        bottom_packs=_format_packs(bottom_packs),
    )

    resp = llm.complete_json(
        role=LLMRole.REVIEWER,
        system=system,
        user=user,
        max_tokens=8192,
    )
    report = ReviewReport.model_validate(resp)
    log.info("reviewer.done", rules=len(report.extracted_rules))
    return report


def write_weekly_log(report: ReviewReport, iso_week: str) -> None:
    """把 ReviewReport 序列化成 markdown 写到 experience_log/。

    只写一份提案，等人工 review 合入 categories/*.md。
    """
    filename = f"{iso_week}.md"
    content = f"""# Experience Log — {iso_week}

**类目**: {report.window.get('category')}
**样本数**: {report.sample_size.get('top', 0)} top, {report.sample_size.get('bottom', 0)} bottom
**窗口**: {report.window.get('start')} → {report.window.get('end')}

## Summary for humans

{report.summary_for_humans}

## Extracted Rules

{_format_rules(report.extracted_rules)}

## Cross-pack Contrast

```json
{_format_json(report.cross_pack_contrast)}
```

## Open Questions

{_format_bullets(report.open_questions)}

---

_本文件由 Reviewer Agent 自动生成，等待人工 review。_
"""
    path = knowledge.write_experience_log(filename, content)
    log.info("reviewer.log_written", path=str(path))


# --- helpers ---

def _format_packs(packs: list[CaseRecord]) -> str:
    if not packs:
        return "(无)"
    import json
    out = []
    for p in packs:
        # Keep it compact; full details would blow the context window
        summary = {
            "pack_id": str(p.pack_id),
            "topic": p.topic,
            "tier": p.tier.value if p.tier else None,
            "l2": p.topic_l2.value,
            "metrics": p.metrics.model_dump() if p.metrics else None,
            "cards_preview": [
                {
                    "pos": c.position,
                    "segment": c.segment.value if hasattr(c.segment, "value") else c.segment,
                    "overlay": c.text_overlay_hint.content_suggestion if c.text_overlay_hint else None,
                }
                for c in p.cards[:10]  # first 10 only to save tokens
            ],
        }
        out.append(json.dumps(summary, ensure_ascii=False, indent=2))
    return "\n\n".join(out)


def _format_rules(rules) -> str:
    if not rules:
        return "(无)"
    return "\n".join(
        f"- **{r.id}** ({r.polarity}, {r.evidence_strength}): {r.rule}\n"
        f"  - scope: {r.scope}\n"
        f"  - target: `{r.target_file}`\n"
        f"  - evidence: {', '.join(r.evidence_packs)}"
        for r in rules
    )


def _format_bullets(items: list[str]) -> str:
    if not items:
        return "(无)"
    return "\n".join(f"- {x}" for x in items)


def _format_json(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)
