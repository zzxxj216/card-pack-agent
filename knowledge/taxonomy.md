# Taxonomy — Three-layer classification

**Last updated**: v0.2 — English rewrite, broader coverage across L1s.

---

## Design principles

The three layers are **orthogonal dimensions**, not a containment hierarchy.
A card pack carries tags on all three layers independently; any layer can be
filtered and searched on its own.

For retrieval, prefer a two-stage approach: hard-filter on L2 (narrative
mechanism), rank within candidates by L1 embedding, and apply L3 as
generation-time constraints.

---

## L1 — Content Domain

| Tag | Definition | Includes | Does NOT include (goes elsewhere) |
|---|---|---|---|
| `festival` | Holiday / anniversary / calendar-specific day as core narrative or time anchor | Western holidays, cultural holidays, personal anniversaries, season turns | Trending news happening on a holiday (→ `trending_event`) |
| `trending_event` | A current news story / public event as the core | Breaking news, social events, celebrity moments, sports moments | Interpretive emotional take (→ `emotional`) |
| `emotional` | Emotion / psychological state as the core, independent of external events | Loneliness, burnout, anxiety, healing, resonance | Emotion triggered by a specific event (→ the event's L1) |
| `knowledge` | Knowledge / skill / information as the core | Explainers, tutorials, trivia, lists | Personal experience sharing (→ `growth`) |
| `character` | A specific person (real or fictional) as the core | Bio, character reading, historical figure | News about a person (→ `trending_event`) |
| `relationship` | Person-to-person dynamics as the core | Family, friendship, romance, workplace | Family narrative inside a holiday (→ `festival`) |
| `growth` | Personal growth / experience / reflection as the core | Life lessons, phase realizations, transformation stories | Method / tutorial content (→ `knowledge`) |

**When a topic straddles multiple L1s**, pick the **dominant narrative driver**.
Example: a "I wish I'd understood my mom sooner" story on Mother's Day is
dominantly festival (→ `festival`). The same story on a random day is
dominantly relationship (→ `relationship`).

---

## L2 — Narrative Mechanism

This layer predicts viral structure better than L1 does.

| Tag | Core drive | Typical opener | Typical closer |
|---|---|---|---|
| `resonance_healing` | Resonance + healing: viewer feels understood, treated gently | "have you ever..." | "it's not just me" |
| `regret_sting` | Regret sting: triggers nostalgia / loss / too-late feeling | "if I had known..." | "I can't go back" |
| `contrast_twist` | Contrast reversal: set up one frame, then flip the expectation | "it looks like A..." | "but actually B" |
| `blessing_ritual` | Direct blessing, warm + positive | "may you..." | "wishing you..." |
| `utility_share` | Utility / share-worthy list / checklist / gift guide | "gift guide for..." | "save / share this" |
| `aphorism_lesson` | Aphorism / lesson, conclusion-style | "the thing is..." | "remember this" |
| `conflict_tension` | Conflict tension between expectation / reality / norms | "while everyone else..." | "meanwhile, me..." |

A pack may mix mechanisms, but one must dominate. Tag with the dominant one.

---

## L3 — Execution Attributes

Enumerated label set; a pack can carry several. Not used for hard
classification — only for generation constraints and fine-grained retrieval.

### Palette
- `palette:warm` `palette:cool` `palette:neutral` `palette:high_contrast`

### Text density
- `text:minimal` (single short phrase per card)
- `text:medium` (2-3 lines)
- `text:heavy` (paragraph-level)

### Subject
- `subject:single_object` (single prop: a cup, a chair)
- `subject:single_person` `subject:multi_person`
- `subject:scene` (scene, no people)
- `subject:text_only` (pure typography)

### Pace
- `pace:slow` (long dwell, immersive emotion)
- `pace:medium`
- `pace:fast` (quick cuts, information-dense)

### CTA strength
- `cta:none` `cta:soft` (comment prompt) `cta:hard` (share / save / follow)

### Style
- `style:realistic`
- `style:illustration`
- `style:collage`
- `style:typographic`

---

## Full examples

### Thanksgiving · the one who couldn't make it home
```yaml
l1: festival
l2: resonance_healing
l3:
  - palette:warm
  - text:minimal
  - subject:single_object    # a plate set aside, an empty chair
  - pace:slow
  - cta:soft
  - style:realistic
```

### Mother's Day · the things I never got to say
```yaml
l1: festival
l2: regret_sting
l3:
  - palette:warm
  - text:medium
  - subject:scene            # reading glasses on a closed book
  - pace:slow
  - cta:none
  - style:realistic
```

### Christmas · last-minute gift guide (under $30)
```yaml
l1: festival
l2: utility_share
l3:
  - palette:high_contrast
  - text:heavy
  - subject:single_object    # flatlay product shots
  - pace:fast
  - cta:hard
  - style:typographic
```

### Random Tuesday · burnout at 28
```yaml
l1: emotional
l2: resonance_healing
l3:
  - palette:cool
  - text:minimal
  - subject:scene            # desk lamp on at 11pm
  - pace:slow
  - cta:soft
  - style:realistic
```

### Oscars night · the speech everyone missed
```yaml
l1: trending_event
l2: contrast_twist
l3:
  - palette:high_contrast
  - text:medium
  - subject:single_person
  - pace:medium
  - cta:soft
  - style:realistic
```

---

## Tagging workflow (Phase 0 mandatory)

1. Every new topic / pack is labeled independently by **two people**
2. If L1 + L2 combinations agree → enter the store as-is
3. If they disagree → discuss now and update the boundary definitions in
   this file (never leave ambiguity)
4. Monthly: review label distribution. Collapse tags that are too sparse.

---

## Changelog

| Date | Version | Change |
|---|---|---|
| 2026-04-17 | v0.1 | Initial CN version |
| 2026-04-19 | v0.2 | English rewrite; examples re-grounded on overseas TikTok (Thanksgiving, Christmas, Mother's Day, burnout, Oscars) |
