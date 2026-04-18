"""Planner Agent — 唯一的大脑。

职责：分类 + 检索 + 产出 strategy doc。
使用 structured_call 保证输出严格符合 StrategyDoc schema。
"""
from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from ..llm import LLMRole
from ..memory.knowledge_loader import knowledge
from ..schemas import ClarificationRequest, StrategyDoc, TopicInput
from ..structured_output import (
    CallMeta,
    StructuredCallError,
    structured_call,
)
from ..tools.retrieve import retrieve_similar_packs

log = structlog.get_logger()


class PlannerOutput(BaseModel):
    """Permissive wrapper for Planner's two output shapes.

    We split on clarification_needed rather than using a discriminated
    union — LLMs forget the discriminator field too often.
    """

    # Clarification path
    clarification_needed: bool | None = None
    questions: list[str] = Field(default_factory=list)

    # Strategy path
    version: str | None = None
    topic: str | None = None
    classification: dict | None = None
    referenced_cases: list[dict] = Field(default_factory=list)
    structure: dict | None = None
    visual_direction: dict | None = None
    copy_direction: dict | None = None
    avoid: list[str] = Field(default_factory=list)
    script_hint: dict | None = None

    def resolve(self) -> StrategyDoc | ClarificationRequest:
        if self.clarification_needed:
            return ClarificationRequest(
                clarification_needed=True,
                questions=self.questions or ["(planner did not supply questions)"],
            )
        return StrategyDoc.model_validate(self.model_dump(exclude_none=True))


SYSTEM_PROMPT_TEMPLATE = """你是卡贴包生成系统的规划 Agent。

{global_context}

---

# 类目专属规则（本次话题所属类目）

{category_playbook}

---

# 最近经验（本类目合并的教训）

{recent_experiences}

---

# 输出要求

你可以输出两种格式之一：

**格式 A — 完整 strategy doc**（正常情况）：
严格按照下方 Output Schema，纯 JSON，无 markdown fence，无前后解释。

**格式 B — 请求澄清**（话题信息不足以分类时）：
{{"clarification_needed": true, "questions": ["问题1", "问题2"]}}

不要两种都输出，也不要混合。

## Output Schema (strategy_doc)

你必须严格输出以下 JSON 结构，字段名不可更改、不可省略、不可新增：

```json
{{
  "version": "1.0",
  "topic": "原话题文本（字符串）",
  "classification": {{
    "l1": "festival",
    "l2": "resonance_healing",
    "l3": ["palette:warm", "text:minimal", ...],
    "reasoning": "为什么选这个分类（1-2 句）"
  }},
  "referenced_cases": [],
  "structure": {{
    "total_cards": 50,
    "segments": [
      {{"range": [1, 3], "role": "hook", "notes": "..."}},
      {{"range": [4, 15], "role": "setup", "notes": "..."}},
      {{"range": [16, 35], "role": "development", "notes": "..."}},
      {{"range": [36, 45], "role": "turn", "notes": "..."}},
      {{"range": [46, 50], "role": "close", "notes": "..."}}
    ]
  }},
  "visual_direction": {{
    "palette": ["#F5A623", "#E8824A", "#FFF8E7"],
    "main_subject": "...",
    "composition_note": "...",
    "style_anchor": "film photography, 35mm, natural light"
  }},
  "copy_direction": {{
    "tone": "克制、温柔、具体",
    "text_density": "minimal",
    "pronoun": "你",
    "hook_type": "独立意象 + 错位时态",
    "cta": {{"intensity": "soft", "example": "..."}}
  }},
  "avoid": [
    "全家团圆刻板叙事",
    "连续三张以上情绪渲染词"
  ],
  "script_hint": {{
    "narrative_arc": "一人 → 场景 → 回忆 → 当下 → 留白",
    "pacing_note": "1.5-2s 每张，32-35s 总时长"
  }}
}}
```

关键约束：
- "topic" 必须是字符串，不是对象
- "structure.segments[].role" 只能是: hook, setup, development, turn, close
- "visual_direction.palette" 是颜色 hex 字符串数组
- "copy_direction.cta" 必须包含 "intensity" 和 "example"
- 不要添加 schema 中没有的字段
"""


USER_PROMPT_TEMPLATE = """# 新话题

原始输入：{raw_topic}

输入类型：{input_type}

附加信息：
{extra_context}

# 检索到的相似高分案例

{retrieved_cases}

# 你的任务

按上方 Output Schema 产出 strategy_doc JSON。注意：
- 纯 JSON，不要 markdown fence，不要前后解释
- topic 字段是字符串
- segments 的 role 只能是 hook/setup/development/turn/close
"""


def plan(
    topic_input: TopicInput,
    hint_l1: str | None = None,
    hint_l2: str | None = None,
) -> tuple[StrategyDoc | ClarificationRequest, CallMeta]:
    """Generate strategy doc (or clarification request).

    :returns: (result, call_meta) — meta includes token/cost info
    """
    log.info("planner.start", topic=topic_input.raw_topic,
             hint_l1=hint_l1, hint_l2=hint_l2)

    # Retrieval (skipped when no L1 hint)
    retrieved = []
    if hint_l1:
        from ..schemas import L1, L2, Tier
        try:
            l1_enum = L1(hint_l1)
            l2_enum = L2(hint_l2) if hint_l2 else None
            retrieved = retrieve_similar_packs(
                topic=topic_input.raw_topic,
                l1=l1_enum,
                l2=l2_enum,
                tier_gte=Tier.GOOD,
                top_k=3,
            )
        except ValueError:
            log.warning("planner.invalid_hint", l1=hint_l1, l2=hint_l2)

    category_md = (
        knowledge.for_category(hint_l1) if hint_l1
        else "(类目未指定，按通用规则生成)"
    )
    recent = knowledge.recent_experiences_summary(max_files=2)

    system = SYSTEM_PROMPT_TEMPLATE.format(
        global_context=knowledge.global_context(),
        category_playbook=category_md,
        recent_experiences=recent,
    )
    user = USER_PROMPT_TEMPLATE.format(
        raw_topic=topic_input.raw_topic,
        input_type=topic_input.input_type,
        extra_context=topic_input.extra_context or "(无)",
        retrieved_cases=_format_retrieved(retrieved),
    )

    try:
        raw_output, meta = structured_call(
            role=LLMRole.PLANNER,
            system=system,
            user=user,
            output_model=PlannerOutput,
            max_tokens=4096,
            temperature=0.3,
            max_repair_attempts=2,
        )
    except StructuredCallError as e:
        log.error("planner.exhausted", error=str(e), call_id=e.meta.call_id)
        raise

    result = raw_output.resolve()
    if isinstance(result, StrategyDoc):
        log.info("planner.done",
                 l1=str(result.classification.l1),
                 l2=str(result.classification.l2),
                 cost_usd=meta.estimated_cost_usd)
    else:
        log.info("planner.clarification", n_questions=len(result.questions))

    return result, meta


def _format_retrieved(hits: list) -> str:
    if not hits:
        return "(无同类案例，按照通用规则生成)"
    lines = []
    for h in hits:
        lines.append(
            f"- case_id={h.id} score={h.score:.3f} "
            f"topic={h.payload.get('topic', '?')} "
            f"tier={h.payload.get('tier', '?')} "
            f"l2={h.payload.get('l2', '?')}"
        )
    return "\n".join(lines)
