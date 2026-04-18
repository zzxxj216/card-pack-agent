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


SCRIPT_SYSTEM_TEMPLATE = """你是视频分镜脚本生成器。

{global_style_guide}

---

# 类目专属节奏

{category_playbook}

---

# 文案禁忌

{anti_patterns}

---

# 输出规则

输出必须是纯 JSON 对象，无 markdown fence，无前后解释。

严格按照以下 schema：

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

- shots 数量必须等于卡贴数量
- position 从 1 开始连续
- duration_s: hook 卡 0.8-1.2s，普通卡 1.2-2.0s
"""

SCRIPT_USER_TEMPLATE = """# Strategy Doc

{strategy_doc_json}

# 已生成的卡贴（精简版）

{cards_json}

# 你的任务

产出完整分镜脚本，每张卡贴对应一个 shot。
- 总时长目标：{target_duration}s
- shots 数量必须等于 {n_cards}
- 所有 position 从 1 到 {n_cards}，不得缺失或重复
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
