# Category Playbook: Trending Event

**L1**: `trending_event`
**Status**: v0.2 — Minimal scaffold. Unverified mechanism recipes, visual
notes, and open-question speculation removed. Mechanism selection is now
topic-driven.
**Validation progress**: 0 / 30 packs

---

## 1. Scope

### 1.1 In scope
- Packs anchored on a **current / recent public event** as the narrative core
- Examples:
  - Award shows (Oscars, Grammys, VMAs, Emmys) — specific moments
  - Sports moments (game-winning play, post-match moment, Olympics)
  - Pop-culture drops (album release, film release, viral creator moment)
  - Public figures saying / doing something that's actively trending
  - News-cycle events with short decay curves (48-72h relevance)

### 1.2 Out of scope
- Political / partisan news → **skip entirely** (see anti-patterns §1.2)
- Disasters, tragedies, acts of violence → skip or condolence-only frame;
  do not convert into "content"
- Evergreen emotional pieces that happen to reference a past event →
  `emotional` or `relationship`
- Holiday-coincident events → `festival` unless the event dwarfs the holiday

### 1.3 Compliance gates (non-negotiable)
- If the event involves **loss of life**, the only acceptable frame is
  condolence / memorial, no humor, no reversal, no CTA beyond comment-of-
  respect
- Do not speculate on facts not yet confirmed by reputable sources
- Avoid impersonating involved parties

---

## 2. Speed matters — decay curve

Trending content has a **decay half-life of ~24 hours** on TikTok. The
operator should aim for:

- Planner call → publish < 4 hours total for hot moments
- Skip the pack entirely if you're >48 hours past the peak unless you have a
  genuinely new angle

If we can't ship inside the window, reclassify to `emotional` /
`aphorism_lesson` with the event as backdrop.

---

## 3. Category-specific taboos

1. **No "how to monetize this trend" openers** — reads crass fast
2. **No speculation** presented as fact; use "according to X..." framing
3. **No impersonating** involved parties (no "as [celebrity] I would...")
4. **No partisan takes** on elections, officials, legislation — we do not
   play this space
5. **No making content of tragedies** (school shootings, natural disasters,
   hate crimes, deaths-in-the-news) — condolence-only or skip
6. **Avoid recency-inflating language** ("this just happened" for something
   12h old) — audiences check timestamps
7. **Claim accuracy**: if we can't source it with a reputable outlet in
   < 2 minutes, we don't make the pack

---

## Changelog

| Date | Version | Change |
|---|---|---|
| 2026-04-19 | v0.1 | Initial English draft |
| 2026-04-21 | v0.2 | Removed unverified §3 success-pattern recipes, §4 mechanism-avoidance claims, §6 visual notes, §7 open questions; kept only scope, decay-curve operational rules, and taboos |
