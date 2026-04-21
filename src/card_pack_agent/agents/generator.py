"""Generator Agent — 执行层。

- generate_cards: 代理到 generator_cards_batched（分批生成）
- generate_script: 脚本一次性生成（量小，一般不会超 token）
"""
from __future__ import annotations

import structlog

from ..llm import LLMRole
from ..memory.knowledge_loader import knowledge
from ..schemas import CardPrompt, Script, StrategyDoc
from ..structured_output import CallMeta, structured_call
from .generator_cards_batched import generate_cards_batched

log = structlog.get_logger()


SCRIPT_SYSTEM_TEMPLATE = """You are a teaser-video script generator for a TikTok card pack.

The product is a pack of ~50 stickers. Only a small subset of those cards will
appear in the ≤15-second teaser video that hooks viewers to the full pack.
Your job is to pick that subset and sequence it.

The target audience is English-speaking overseas viewers. All free-text fields
(notes, craft_note, bgm_suggestion fields) must be written in English.

{global_style_guide}

---

# Category pacing playbook

{category_playbook}

---

# Copy anti-patterns

{anti_patterns}

---

# Output rules

Output a raw JSON object. No markdown fence, no prose before or after.

Follow this schema exactly:

```
{{
  "total_duration_s": <sum of all shot.duration_s values, in seconds; must be <= 15.0>,
  "bgm_suggestion": {{
    "mood": "ambient calm",
    "reference": "lo-fi piano, soft ambient",
    "tempo_curve": "slow start, build at 60%"
  }},
  "has_voiceover": false,
  "shots": [
    {{
      "position": <card position, i.e. an integer from the actual 50-card pack>,
      "duration_s": 1.8,
      "notes": ""
    }}
  ],
  "key_moments": [
    {{
      "position": <one of the shot positions above>,
      "role": "hook",
      "craft_note": "why this moment carries the pack"
    }}
  ]
}}
```

Selection rules (NON-NEGOTIABLE):
- **Pick 6 to 10 cards** from the full pack. This is a teaser, not a playback.
  Fewer than 6 is too thin; more than 10 breaks the 15-second budget.
- Each `shot.position` MUST reference a real card position from the generated
  pack (1..50). Never invent positions.
- The subset MUST cover the narrative arc — include:
  - at least one card from the **hook** segment (positions 1-3)
  - at least one card from the **turn** segment
  - at least one card from the **close** segment
  - the remaining 3-7 slots come from setup / development highlights you
    judge as most representative of the pack
- Shots in `shots[]` must be ordered by ascending `position` unless the
  pack's L2 mechanism is `contrast_twist`, in which case you may place the
  reversal card out of order for impact.

Duration rules:
- `duration_s` is the on-screen time for ONE card in **seconds**
  (not milliseconds, not a fraction of the total)
- Hard per-shot range: **1.0 to 2.5 seconds**. Viewers need ~1.2s to read
  overlay copy; anything shorter is unreadable.
- `total_duration_s` MUST equal the arithmetic sum of every `shot.duration_s`
  AND must be **<= 15.0 seconds** (hard cap).
- Keep `shot.notes` as `""` for every non-key_moment shot. Only
  `key_moments[].craft_note` carries text, to stay within the token budget.
"""

SCRIPT_USER_TEMPLATE = """# Strategy Doc

{strategy_doc_json}

# Full pack cards (compact form — all {n_cards} cards; pick 6-10 of these)

{cards_json}

# Your task

Produce a 15-second teaser shot-list.
- Total duration: ≤ 15.0 seconds (hard cap)
- Shots count: **6 to 10** (pick the most representative cards)
- Each `shot.position` must be one of the card positions shown above
- Include at least one hook / turn / close card; fill the rest with
  high-signal setup or development cards
- All free-text fields in English
"""


def generate_cards(strategy: StrategyDoc) -> tuple[list[CardPrompt], CallMeta]:
    """Delegate to batched generator. Returns (cards, meta)."""
    return generate_cards_batched(strategy, batch_size=12)


SHOT_MIN_S = 1.0
SHOT_MAX_S = 2.5
TOTAL_MAX_S = 15.0
SHOTS_MIN = 6
SHOTS_MAX = 10


def generate_script(
    strategy: StrategyDoc, cards: list[CardPrompt],
) -> tuple[Script, CallMeta]:
    """Generate a ≤15s teaser shot-list that picks 6-10 cards from the pack."""
    log.info("generator.script.start", n_cards=len(cards))

    n_cards = len(cards)
    valid_positions = {c.position for c in cards}

    system = SCRIPT_SYSTEM_TEMPLATE.format(
        global_style_guide=knowledge.global_style_guide(),
        category_playbook=knowledge.for_category(_l1_value(strategy)),
        anti_patterns=knowledge.global_anti_patterns(),
    )
    user = SCRIPT_USER_TEMPLATE.format(
        strategy_doc_json=strategy.model_dump_json(),
        cards_json=_cards_compact(cards),
        n_cards=n_cards,
    )

    script, meta = structured_call(
        role=LLMRole.GENERATOR,
        system=system,
        user=user,
        output_model=Script,
        max_tokens=4096,
        temperature=0.5,
        max_repair_attempts=2,
    )

    script.shots = _repair_shots(script.shots, valid_positions)
    _repair_durations(script)

    log.info("generator.script.done",
             shots=len(script.shots),
             total_duration=script.total_duration_s,
             cost_usd=meta.estimated_cost_usd)
    return script, meta


def _repair_shots(shots, valid_positions: set[int]):
    """Drop shots referencing non-existent positions, dedupe, cap at 10."""
    seen: set[int] = set()
    cleaned = []
    dropped_invalid = []
    for s in shots:
        if s.position not in valid_positions:
            dropped_invalid.append(s.position)
            continue
        if s.position in seen:
            continue
        seen.add(s.position)
        cleaned.append(s)
    if dropped_invalid:
        log.warning("generator.script.dropped_invalid_positions",
                    positions=dropped_invalid[:10])
    if len(cleaned) > SHOTS_MAX:
        log.warning("generator.script.too_many_shots",
                    got=len(cleaned), capped=SHOTS_MAX)
        cleaned = cleaned[:SHOTS_MAX]
    if len(cleaned) < SHOTS_MIN:
        log.warning("generator.script.too_few_shots",
                    got=len(cleaned), min=SHOTS_MIN)
    return cleaned


def _repair_durations(script: Script) -> None:
    """Clamp each shot to [1.0, 2.5]s; ensure sum ≤ 15s by proportional scale."""
    repaired = 0
    for shot in script.shots:
        if shot.duration_s < SHOT_MIN_S or shot.duration_s > SHOT_MAX_S:
            repaired += 1
            shot.duration_s = max(SHOT_MIN_S, min(SHOT_MAX_S, shot.duration_s))

    total = round(sum(s.duration_s for s in script.shots), 2)

    if total > TOTAL_MAX_S and script.shots:
        scale = TOTAL_MAX_S / total
        for shot in script.shots:
            shot.duration_s = max(SHOT_MIN_S, round(shot.duration_s * scale, 2))
        total = round(sum(s.duration_s for s in script.shots), 2)
        log.warning("generator.script.scaled_to_cap",
                    capped_total=TOTAL_MAX_S, achieved=total)

    if repaired or abs(total - script.total_duration_s) > 0.5:
        log.warning(
            "generator.script.duration_repaired",
            clamped_shots=repaired,
            old_total=script.total_duration_s,
            new_total=total,
            n_shots=len(script.shots),
        )
    script.total_duration_s = total


# --- helpers ---

def _l1_value(strategy: StrategyDoc) -> str:
    v = strategy.classification.l1
    return v.value if hasattr(v, "value") else str(v)


def _cards_compact(cards: list[CardPrompt]) -> str:
    """Ultra-compact summary of cards for script generation context."""
    import json
    compact = [
        {
            "position": c.position,
            "segment": c.segment.value if hasattr(c.segment, "value") else c.segment,
            "overlay": (
                c.text_overlay_hint.content_suggestion
                if c.text_overlay_hint else None
            ),
        }
        for c in cards
    ]
    return json.dumps(compact, ensure_ascii=False)

