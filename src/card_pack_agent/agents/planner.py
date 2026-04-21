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


SYSTEM_PROMPT_TEMPLATE = """You are the Planner Agent for a TikTok card-pack generation system.

The product targets an overseas (English-speaking) audience. All generated copy,
overlay text, tone descriptions, avoid-lists, and free-form notes MUST be written
in English. JSON field names, enum values, and hex colors stay as-is.

{global_context}

---

# Category playbook (for this topic's L1)

{category_playbook}

---

# Recent experience (merged lessons for this category)

{recent_experiences}

---

# Recent human rejections (what reviewers shot down — avoid these patterns)

{recent_rejections}

---

# Output contract

You must output ONE of two shapes:

**Shape A — full strategy_doc** (normal case):
Follow the schema below exactly. Raw JSON, no markdown fence, no prose before
or after.

**Shape B — clarification request** (topic is too ambiguous to classify):
{{"clarification_needed": true, "questions": ["question 1", "question 2"]}}

Do not output both. Do not mix.

## Output Schema (strategy_doc)

Allowed enum values (enum order is arbitrary — do NOT default to the first
option and do NOT copy whatever value the example below happens to show):
- `classification.l1` ∈ {{festival, trending_event, emotional, knowledge, character, relationship, growth}}
- `classification.l2` ∈ {{resonance_healing, regret_sting, contrast_twist, blessing_ritual, utility_share, aphorism_lesson, conflict_tension}}
- `structure.segments[].role` ∈ {{hook, setup, development, turn, close}}
- `copy_direction.cta.intensity` ∈ {{none, soft, hard}}

For L2 specifically: evaluate ALL 7 mechanisms against the topic before
committing. Different topics of the same L1 should land on different L2s
depending on tone, audience shape, and what the topic itself rewards —
there is no global preferred mechanism per L1.

Emit exactly this JSON structure. Field names are fixed — do not rename,
omit, or add fields. In the example below, `<angle-bracketed>` strings are
PLACEHOLDERS — replace them with a concrete choice; never emit the literal
placeholder text.

```json
{{
  "version": "1.0",
  "topic": "verbatim topic text (string)",
  "classification": {{
    "l1": "<one of the l1 enum values, picked on topic merit>",
    "l2": "<one of the l2 enum values, picked after considering all 7>",
    "l3": ["palette:<warm|cool|neutral>", "text:<minimal|medium|dense>", ...],
    "reasoning": "why this classification (1-2 sentences)"
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
    "main_subject": "single focal object or tight cluster (NOT a scene) — e.g. 'a folded pair of reading glasses', 'a hand holding a worn photograph', 'a small steaming bowl'. Must be describable as a floating sticker, not placed in any environment.",
    "composition_note": "sticker-ready isolation: subject centered with ~10% margin on a plain near-white backdrop; no floor/wall/table/room; soft studio lighting; aesthetic cues (grain, watercolor, etc.) apply to subject texture only",
    "style_anchor": "die-cut sticker, soft film-grain texture, isolated on plain off-white background"
  }},
  "copy_direction": {{
    "tone": "restrained, tender, specific",
    "text_density": "minimal",
    "pronoun": "you",
    "hook_type": "standalone image + temporal dissonance",
    "cta": {{"intensity": "soft", "example": "..."}}
  }},
  "avoid": [
    "stereotypical family-reunion narrative",
    "3+ consecutive cards with emotional hype words"
  ],
  "script_hint": {{
    "narrative_arc": "one person -> scene -> memory -> present -> silence",
    "pacing_note": "1.5-2s per card, 32-35s total"
  }}
}}
```

Hard constraints:
- "topic" must be a string, not an object
- "structure.segments[].role" only allows: hook, setup, development, turn, close
- "visual_direction.palette" is an array of hex color strings
- "copy_direction.cta" must contain "intensity" and "example"
- All free-text fields (tone, reasoning, notes, avoid items, composition_note,
  hook_type, narrative_arc, pacing_note, cta.example, main_subject) must be
  written in English
- Do not add fields not in the schema

Sticker-output constraint (NON-NEGOTIABLE):
- The pack ships as 50 stickers a viewer pastes into TikTok videos. Every card
  is a single isolated subject on a plain near-white backdrop, never a scene.
- "visual_direction.main_subject" must name a single object or tight subject
  cluster describable as a floating sticker. NEVER name an environment, room,
  landscape, or scenic setting.
- "visual_direction.composition_note" must describe sticker-ready isolation
  (subject centered on clean backdrop with margin for die-cut). NEVER describe
  scene framing, background environments, or environmental shadows.
- "visual_direction.style_anchor" should read as a TEXTURE/aesthetic cue
  applied to the subject (e.g. "soft film-grain texture, muted warm tones,
  die-cut sticker") — not as a photo-of-scene phrase.
"""


USER_PROMPT_TEMPLATE = """# New topic

Raw input: {raw_topic}

Input type: {input_type}

Extra context:
{extra_context}

# Operator classification hints

{operator_hints}

# Retrieved similar high-scoring cases

{retrieved_cases}

# Your task

Produce a strategy_doc JSON per the schema above. Reminders:
- Raw JSON, no markdown fence, no prose before or after
- "topic" is a string
- segments[].role must be one of hook/setup/development/turn/close
- All free-text fields in English
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

    from .. import feedback as feedback_mod
    reject_hints = feedback_mod.recent_avoid_hints(limit=6)
    rejections_block = (
        "\n".join(f"- {h}" for h in reject_hints)
        if reject_hints
        else "(no human rejections recorded yet)"
    )

    system = SYSTEM_PROMPT_TEMPLATE.format(
        global_context=knowledge.global_context(),
        category_playbook=category_md,
        recent_experiences=recent,
        recent_rejections=rejections_block,
    )
    hint_lines = []
    if hint_l1:
        hint_lines.append(f"- L1 hint: `{hint_l1}` (operator-specified content domain)")
    if hint_l2:
        hint_lines.append(f"- L2 hint: `{hint_l2}` (operator-specified narrative mechanism)")
    if hint_lines:
        operator_hints = (
            "\n".join(hint_lines)
            + "\n\nHonor these hints unless the topic is clearly incompatible. "
            "If overriding, justify in `classification.reasoning`."
        )
    else:
        operator_hints = (
            "(no operator hints — evaluate all L1 and L2 enum values on topic "
            "merit; do not default to any single mechanism)"
        )

    user = USER_PROMPT_TEMPLATE.format(
        raw_topic=topic_input.raw_topic,
        input_type=topic_input.input_type,
        extra_context=topic_input.extra_context or "(无)",
        operator_hints=operator_hints,
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
