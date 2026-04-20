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


SCRIPT_SYSTEM_TEMPLATE = """You are a video shot-list / script generator for a TikTok card pack.

The product targets an English-speaking overseas audience. All free-text fields
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
  "total_duration_s": 40.0,
  "bgm_suggestion": {{
    "mood": "ambient calm",
    "reference": "lo-fi piano, soft ambient",
    "tempo_curve": "slow start, build at 60%"
  }},
  "has_voiceover": false,
  "shots": [
    {{
      "position": 1,
      "duration_s": 1.5,
      "notes": "hook shot"
    }}
  ],
  "key_moments": [
    {{
      "position": 1,
      "role": "hook",
      "craft_note": "..."
    }}
  ]
}}
```

- `shots` count must equal the number of cards
- `position` is 1-indexed and continuous
- `duration_s`: hook cards 0.8-1.2s, normal cards 1.2-2.0s
- Keep `shot.notes` empty (`""`) for every non-key_moment shot to stay within
  token budget. Only key_moments carry a `craft_note`.
"""

SCRIPT_USER_TEMPLATE = """# Strategy Doc

{strategy_doc_json}

# Generated cards (compact form)

{cards_json}

# Your task

Produce a full shot-list script, one shot per card.
- Target total duration: {target_duration}s
- `shots` count must equal {n_cards}
- All positions span 1..{n_cards} with no gaps or duplicates
- All free-text fields in English
"""


def generate_cards(strategy: StrategyDoc) -> tuple[list[CardPrompt], CallMeta]:
    """Delegate to batched generator. Returns (cards, meta)."""
    return generate_cards_batched(strategy, batch_size=12)


def generate_script(
    strategy: StrategyDoc, cards: list[CardPrompt],
) -> tuple[Script, CallMeta]:
    """Generate script with structured_call + validation."""
    log.info("generator.script.start")

    target = _parse_target_duration(strategy.script_hint.pacing_note)
    n_cards = len(cards)

    system = SCRIPT_SYSTEM_TEMPLATE.format(
        global_style_guide=knowledge.global_style_guide(),
        category_playbook=knowledge.for_category(_l1_value(strategy)),
        anti_patterns=knowledge.global_anti_patterns(),
    )
    user = SCRIPT_USER_TEMPLATE.format(
        strategy_doc_json=strategy.model_dump_json(),
        cards_json=_cards_compact(cards),
        target_duration=target,
        n_cards=n_cards,
    )

    script, meta = structured_call(
        role=LLMRole.GENERATOR,
        system=system,
        user=user,
        output_model=Script,
        max_tokens=8192,
        temperature=0.5,
        max_repair_attempts=2,
    )

    # Post-validate shot count
    if len(script.shots) != n_cards:
        log.warning("generator.script.shot_count_mismatch",
                    got=len(script.shots), expected=n_cards)
        # Pad or trim so downstream Evaluator can still run
        script.shots = script.shots[:n_cards]

    log.info("generator.script.done",
             shots=len(script.shots),
             total_duration=script.total_duration_s,
             cost_usd=meta.estimated_cost_usd)
    return script, meta


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


def _parse_target_duration(pacing_note: str) -> int:
    """Best-effort parse 'xx-xx秒' / 'xxs' out of pacing_note."""
    import re
    # Look for patterns like "35-40秒" or "35-40s" or "38 秒"
    m = re.search(r"(\d+)\s*[-~到]\s*(\d+)\s*[秒s]", pacing_note)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (lo + hi) // 2
    m = re.search(r"(\d+)\s*[秒s]", pacing_note)
    if m:
        return int(m.group(1))
    return 40  # default
