# Category Playbook: Festival

**L1**: `festival`
**Status**: v0.2 — English rewrite. Zero-data cold start; every rule here is
extrapolated from general principles and peer observation and is NOT yet
validated on this account's data.
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

## 2. Success patterns (principle-derived, unvalidated)

### 2.1 Resonance + healing (`resonance_healing`)

**When to use**: family distance, solo holidays, the adult dullness around
holidays

**Visual recipe**:
- Warm-led palette: `#F5A623` amber / `#E8824A` soft coral / low-sat cream
- Single-object composition: a mug, a lamp, a worn book, a solo chopstick
  set, a leftover slice
- Soft light, shallow depth of field
- Subject placed low or to one side; lots of negative space above for overlay

**Copy recipe**:
- Main overlay 24-36pt, one sentence
- Short: hook <= 8 English words; body <= 12
- Prefer "you" over "we"
- Avoid blessing cliches ("may you...", "wishing you...")

**Pacing (50 cards)**:
- 1-3: isolated object + piercing one-liner
  ("are you eating dinner alone this year")
- 4-15: scene details (the plate wrapped in foil, the unopened card)
- 16-30: concrete memory / detail deep-dives
- 31-42: a small turn ("but...", "still...")
- 43-50: gentle landing (no lecture, no forced uplift)

### 2.2 Regret sting (`regret_sting`)

**When to use**: Mother's / Father's Day, anniversary of a loss, remembering
elders, first holiday without someone

**Visual recipe**:
- Aged-warm: `#D4A574` old photo / washed-out film look
- Empty-scene objects: an empty chair, an old home corner, an unfinished
  project
- Avoid any "complete-family" frame
- Low contrast, film grain

**Copy recipe**:
- Extreme minimalism, one line per card
- Avoid naming "died / passed / gone"; use the object: the empty chair, the
  uneaten plate, the coat still hanging
- Temporal dissonance: "he always said...", "I thought..."

**Pacing**:
- 1-3: specific-object close-up + dissonant-tense hook
  ("his mug is still in rotation")
- 4-20: detail expansion
- 21-40: reveal section — slowest beat, most negative space
- 41-50: no forced uplift; quiet close (avoid hard CTAs on this mechanism)

### 2.3 Blessing / ritual (`blessing_ritual`)

**When to use**: New Year's, birthdays, graduation, welcome-to-a-new-year

**Visual recipe**:
- Saturated warm palette: red, gold, coral
- Festival symbols: lights, flowers, gifts, fireworks (avoid kitsch overload)
- Multi-person / crowd scenes are allowed; keep the subject clear

**Copy recipe**:
- Blessings are allowed but must be specific: "may this be the year you stop
  apologizing for existing" beats "may your year be bright" 10x
- A slightly longer CTA is acceptable at the close

**Pacing**:
- 1-3: festival symbol + warm hook
- 4-30: specific blessings grouped (for family / friends / yourself...)
- 31-45: emotional peak
- 46-50: closer + CTA

### 2.4 Utility share (`utility_share`)

**When to use**: holiday gift guides, holiday outfit lists, holiday recipes

**Visual recipe**:
- High contrast, information-dense
- Type-driven: large headline + bullet list
- A single card can carry 3-5 info points
- Clean and grid-like; no negative-space aesthetics

**Copy recipe**:
- Listicle headers are fine: "15 to save", "the only list you need"
- Bulleted, short, specific numbers

**Pacing (structure differs from emotional packs)**:
- 1-3: pain-point hook ("stop panic-buying gifts")
- 4-48: list body (even cadence; each card carries 1-2 points)
- 49-50: summary + hard CTA

### 2.5 Conflict tension (`conflict_tension`)

**When to use**: festival vs reality gap (no money, no home, no partner,
still-at-work, estranged-family)

**Visual recipe**:
- Contrast framing: festival symbol + reality scene juxtaposed
- Warm / cool split: warm "them" vs cool "me"
- Split-screen, cut-over, or double-exposure allowed

**Copy recipe**:
- Parallel phrasing: "everyone else..." / "meanwhile, me..."
- Don't self-pity; keep it dry or wry
- Close in silence or with a self-aware joke; no forced uplift

**Pacing**:
- 1-3: hook (counter-intuitive contrast)
- 4-30: contrast unfolds
- 31-45: can pivot toward reconciliation or deepen the contrast
- 46-50: open ending

### 2.6 Contrast twist (`contrast_twist`)

**When to use**: works for most holidays — set up an expectation, then flip

**Visual recipe**:
- Visual language A for the first half; hard switch at the reversal card
- The reversal card should be the strongest visual hit

**Pacing**:
- 1-25: setup (seems to be an A story)
- 26-30: reversal node (the strongest single card)
- 31-50: new perspective unfolds + close

### 2.7 Aphorism / lesson (`aphorism_lesson`)

**Generally NOT recommended** as the primary mechanism for festival packs —
skews preachy. Use sparingly, or embed a short aphorism as a supporting beat
inside another mechanism.

---

## 3. Festival-specific taboos

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

## 4. Related prompt templates

The human-reference templates live at:
- `prompt_templates/generator_cards.v1.md`
- `prompt_templates/generator_script.v1.md`

Note: these `.md` files are for humans. The actual prompts the LLM sees are
hard-coded in `src/card_pack_agent/agents/*.py` — any playbook change must be
reflected in the agent code (see CLAUDE.md §3.1).

---

## 5. Open questions (to be answered by data)

- [ ] Which mechanism performs best for this account's audience? Current
      hypothesis: `resonance_healing` > `regret_sting` > others — pending
      30-pack validation.
- [ ] Warm vs cool palette — actual completion-rate delta?
- [ ] Single-object vs multi-person subjects — festival-category impact?
- [ ] Best hook form: question / standalone-image / counter-framing?
- [ ] Text density (`text:minimal` vs `text:medium`) across mechanisms?
- [ ] Do culturally-rooted festivals (Diwali, Lunar New Year) need
      audience-specific copy registers?

---

## 6. Historical experience (merged from `experience_log`, empty for now)

_This section is merged manually from `experience_log/` weekly. Currently empty._

---

## Changelog

| Date | Version | Change |
|---|---|---|
| 2026-04-17 | v0.1 | Initial CN version (zero-data cold start) |
| 2026-04-19 | v0.2 | Full English rewrite; festival scope expanded to US / global / cultural / respect-required |
