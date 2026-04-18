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


SYSTEM_TEMPLATE = """你是内容复盘 Agent。

{category_playbook}

---

{failure_library}

---

输出必须是纯 JSON，schema 见 knowledge/prompt_templates/reviewer.v1.md。
"""


USER_TEMPLATE = """# 复盘窗口

{window}

类目: {category}
样本: top={n_top}, bottom={n_bottom}

# Top 组 (tier >= good)

{top_packs}

# Bottom 组 (tier <= mid)

{bottom_packs}

# 你的任务

按 reviewer.v1.md 的 4 步产出结构化 ReviewReport。
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
