"""Generator 卡贴分批生成。

原理：一次让 LLM 产 50 张容易被 max_tokens 截断。按 strategy.structure.segments
分批，每批 10-15 张，共享 system prompt 保证风格一致。
"""
from __future__ import annotations

import structlog

from ..llm import LLMRole
from ..memory.knowledge_loader import knowledge
from ..schemas import CardPrompt, StrategyDoc
from ..structured_output import CallMeta, structured_call

log = structlog.get_logger()


CARDS_SYSTEM_TEMPLATE = """你是卡贴 prompt 生成器。

{global_style_guide}

---

# 类目专属规则

{category_playbook}

---

# 视觉禁忌

{anti_patterns}

---

# 输出规则

- 输出必须是纯 JSON 数组，无 markdown fence、无前后解释文字
- 每一项必须严格包含以下字段（不可新增、不可省略）：

```
{{
  "position": 1,
  "segment": "hook",
  "prompt": "film photography, 35mm, ... 完整英文 prompt",
  "negative_prompt": "text, watermark, logo, typography, ...",
  "composition_note": "中文构图说明",
  "text_overlay_hint": {{
    "content_suggestion": "卡贴上要叠加的文字内容",
    "position": "top-center",
    "size_tier": "hook"
  }}
}}
```

关键约束：
- position 必须严格匹配要求的范围
- segment 只能是: hook, setup, development, turn, close
- negative_prompt 必须包含 "text, watermark, logo, typography"
- prompt 不得描述任何要出现在卡贴上的文字，必须是纯英文
- 所有 prompt 必须包含 style_anchor 和 palette 颜色
- text_overlay_hint 必须是对象（不是字符串），包含 content_suggestion、position、size_tier 三个字段
- text_overlay_hint.position 可选值: top-center, top-left, bottom-center, center
- text_overlay_hint.size_tier 可选值: hook, title, body, caption
- 如果该卡不需要文字叠加，text_overlay_hint 设为 null
"""


BATCH_USER_TEMPLATE = """# Strategy Doc

{strategy_doc_json}

# 本批任务

为 position {range_start} 到 {range_end}（共 {n} 张）生成 card prompt。

这些卡贴属于 **{segment_role}** 段，请严格对照 strategy.structure 中该段的 notes。

# 视觉锁定（所有卡必须共享）

- style_anchor: `{style_anchor}`
- palette: {palette}
- main_subject 家族: {main_subject}

# 前面已生成卡贴的风格参考（前 3 张压缩信息，仅供对齐用）

{prev_batch_summary}

# 本批输出

严格 JSON array，{n} 个元素。
"""


def generate_cards_batched(
    strategy: StrategyDoc,
    batch_size: int = 12,
) -> tuple[list[CardPrompt], CallMeta]:
    """Generate all cards by batch, per segment.

    Strategy: iterate over strategy.structure.segments. If a segment is larger
    than batch_size, further split. Each batch is a separate LLM call but
    shares the system prompt and a compact summary of prior cards.
    """
    total_cards = strategy.structure.total_cards
    segments = strategy.structure.segments
    log.info("generator.cards.batched.start",
             total=total_cards, n_segments=len(segments))

    system = CARDS_SYSTEM_TEMPLATE.format(
        global_style_guide=knowledge.global_style_guide(),
        category_playbook=knowledge.for_category(_l1_value(strategy)),
        anti_patterns=knowledge.global_anti_patterns(),
    )

    all_cards: list[CardPrompt] = []
    aggregated_meta = CallMeta(role="generator", model="")

    # Flatten segments into batches, respecting batch_size cap
    batches = _plan_batches(segments, batch_size)

    for i, batch in enumerate(batches):
        start, end, segment_role = batch
        n = end - start + 1
        prev_summary = _summarize_prior_cards(all_cards, max_items=3)

        user = BATCH_USER_TEMPLATE.format(
            strategy_doc_json=strategy.model_dump_json(),
            range_start=start,
            range_end=end,
            n=n,
            segment_role=segment_role,
            style_anchor=strategy.visual_direction.style_anchor,
            palette=", ".join(strategy.visual_direction.palette),
            main_subject=strategy.visual_direction.main_subject,
            prev_batch_summary=prev_summary or "(首批，无参考)",
        )

        log.info("generator.cards.batch",
                 batch=i + 1, total=len(batches), range=(start, end))

        cards, meta = structured_call(
            role=LLMRole.GENERATOR,
            system=system,
            user=user,
            output_model=CardPrompt,
            is_list=True,
            max_tokens=6144,  # enough for 12-15 cards comfortably
            temperature=0.6,
        )

        # Validate positions — LLM sometimes renumbers them
        cards = _repair_positions(cards, start, end)
        all_cards.extend(cards)

        # Aggregate meta
        aggregated_meta.attempts += meta.attempts
        aggregated_meta.input_tokens += meta.input_tokens
        aggregated_meta.output_tokens += meta.output_tokens
        aggregated_meta.total_tokens = (
            aggregated_meta.input_tokens + aggregated_meta.output_tokens
        )
        aggregated_meta.estimated_cost_usd += meta.estimated_cost_usd
        aggregated_meta.model = meta.model

    # Final position sanity check
    positions = [c.position for c in all_cards]
    expected = list(range(1, total_cards + 1))
    if positions != expected:
        log.warning("generator.cards.position_mismatch",
                    got=positions[:20], expected_first_20=expected[:20])
        # Renumber to enforce 1..N
        for new_pos, card in enumerate(all_cards, start=1):
            card.position = new_pos

    log.info("generator.cards.batched.done",
             n_cards=len(all_cards),
             total_cost_usd=aggregated_meta.estimated_cost_usd)
    return all_cards, aggregated_meta


def _plan_batches(
    segments,
    batch_size: int,
) -> list[tuple[int, int, str]]:
    """Flatten segments into (start, end, role) tuples, respecting batch_size."""
    batches: list[tuple[int, int, str]] = []
    for seg in segments:
        seg_start, seg_end = seg.range
        role = seg.role.value if hasattr(seg.role, "value") else str(seg.role)
        cur = seg_start
        while cur <= seg_end:
            batch_end = min(cur + batch_size - 1, seg_end)
            batches.append((cur, batch_end, role))
            cur = batch_end + 1
    return batches


def _summarize_prior_cards(cards: list[CardPrompt], max_items: int = 3) -> str:
    """Compact textual summary of last N cards' style — NOT full prompts.

    This prevents blowing the context window when prior batches already
    produced 30+ cards, while still anchoring the style.
    """
    if not cards:
        return ""
    sample = cards[-max_items:] if len(cards) > max_items else cards
    lines = []
    for c in sample:
        overlay = (
            c.text_overlay_hint.content_suggestion if c.text_overlay_hint else "(无)"
        )
        # Keep each line short
        prompt_snippet = c.prompt[:120] + ("..." if len(c.prompt) > 120 else "")
        lines.append(f"  - pos={c.position} | {prompt_snippet} | overlay={overlay}")
    return "前序卡贴摘要：\n" + "\n".join(lines)


def _repair_positions(
    cards: list[CardPrompt], expected_start: int, expected_end: int,
) -> list[CardPrompt]:
    """LLM sometimes returns positions 1..N instead of start..end. Fix."""
    expected_n = expected_end - expected_start + 1
    if len(cards) == expected_n:
        positions = [c.position for c in cards]
        if positions != list(range(expected_start, expected_end + 1)):
            log.warning("generator.cards.renumbering_batch",
                        got=positions, expected=f"{expected_start}..{expected_end}")
            for i, card in enumerate(cards):
                card.position = expected_start + i
    elif len(cards) < expected_n:
        log.warning("generator.cards.short_batch",
                    got=len(cards), expected=expected_n)
    else:
        log.warning("generator.cards.long_batch",
                    got=len(cards), expected=expected_n)
        cards = cards[:expected_n]
    return cards


def _l1_value(strategy: StrategyDoc) -> str:
    v = strategy.classification.l1
    return v.value if hasattr(v, "value") else str(v)
