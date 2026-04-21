# Category Playbook: Festival

**L1**: `festival`
**Status**: v0.3 — Minimal scaffold. Unverified mechanism recipes and
pacing hypotheses removed. Mechanism selection is now topic-driven; this
file only defines classification scope and category taboos.
**Validation progress**: 0 / 30 packs

---

## 1. Scope

### 1.1 In scope
- Packs anchored on a **holiday / anniversary / calendar-specific day**
- Includes:
  - **US federal & popular**: New Year's, Valentine's, Easter, Mother's Day,
    Father's Day, Independence Day (July 4), Halloween, Thanksgiving,
    Christmas
  - **Global / cultural**: Lunar New Year, Diwali, Ramadan / Eid, Hanukkah,
    Día de Muertos, Mardi Gras, St. Patrick's Day, Pride Month (June)
  - **Respect-required** (treat with care — see anti-patterns): Juneteenth,
    Veterans Day, Memorial Day, MLK Day, 9/11, Holocaust Remembrance,
    Indigenous Peoples' Day
  - **Personal calendar**: birthdays, anniversaries, "one year since..."
  - **Season turns**: first day of spring, New Year's Eve countdown,
    autumn arrival

### 1.2 Out of scope (common misclassifications)
- A **specific news event** that happens during a holiday → `trending_event`
- A holiday appearing as **background scene** while relationship or emotion
  drives the narrative → go with the dominant L1
- Anti-holiday-anxiety method / how-to → `knowledge` or `growth`

### 1.3 Edge cases
- "10 comebacks for when relatives pry on Thanksgiving" → surface-looks
  festival, but it's a **utility / `knowledge`** pack — classify as `knowledge`
- "Spending Christmas alone for the first time" → festival (emotion anchor) →
  `festival`
- "The Super Bowl halftime show last night" → `trending_event`, not festival

---

## 2. Festival-specific taboos

1. **No "whole family reunited" as the default family sample** — see
   `global_anti_patterns.md §3.2`
2. **No "share or you don't care" guilt framing**
3. **Over-emotion ceiling**: 3+ consecutive cards with "cry", "tears",
   "sobbing", "broken", "devastated", "wrecked" → flagged and reworked
4. **Respect-required days** (Memorial Day, Veterans Day, 9/11, MLK Day,
   Holocaust Remembrance, Juneteenth) — no humor / twist / sale CTAs
5. **Gift-guide packs** must not imply "not gifting = not loving"
6. **Saturated openers to avoid**:
   - "On this special day..."
   - "Every [holiday], I think about..."
   - "Happy [holiday]!" as a standalone hook (too flat)
   - "Sending love to everyone who..." (fatigued)

---

## 3. Related prompt templates

The human-reference templates live at:
- `prompt_templates/generator_cards.v1.md`
- `prompt_templates/generator_script.v1.md`

Note: these `.md` files are for humans. The actual prompts the LLM sees are
hard-coded in `src/card_pack_agent/agents/*.py` — any playbook change must be
reflected in the agent code (see CLAUDE.md §3.1).

---

## Changelog

| Date | Version | Change |
|---|---|---|
| 2026-04-17 | v0.1 | Initial CN version (zero-data cold start) |
| 2026-04-19 | v0.2 | Full English rewrite; festival scope expanded to US / global / cultural / respect-required |
| 2026-04-21 | v0.3 | Removed unverified §2 success-pattern recipes and §5 open-question hypotheses (an unvalidated mechanism ranking was biasing planner to collapse to two mechanisms regardless of topic); kept only scope and taboos |
