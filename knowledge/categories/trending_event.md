# Category Playbook: Trending Event

**L1**: `trending_event`
**Status**: v0.1 — Initial English draft. Zero data.
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

## 3. Success patterns (principle-derived)

### 3.1 Contrast twist (`contrast_twist`)

**When to use**: one moment that looked like A turned out to be B

**Visual recipe**:
- First half: visual language of the expected framing
- Reversal card: strongest single-frame hit (stark cut / high contrast /
  text-led)
- Second half: the "real" framing

**Copy**:
- Hook: "everyone thought X happened. look again."
- Avoid sensational "you won't believe..." — reads like clickbait

**Pacing (50 cards)**:
- 1-25: setup (A framing)
- 26-30: reversal node (strongest)
- 31-50: new framing unfolds + close

### 3.2 Aphorism / lesson (`aphorism_lesson`)

**When to use**: the event lends itself to a reusable takeaway

**Visual recipe**:
- Type-led: strong headline cards
- Mix of evidence frames (from the event) + typographic cards

**Copy**:
- One insight per card, max
- Avoid preaching. Let the event carry the evidence.
- Close: one-line takeaway, soft CTA

### 3.3 Conflict tension (`conflict_tension`)

**When to use**: the event exposes a contradiction (expectation vs reality,
establishment vs outsider, hype vs substance)

**Visual recipe**:
- Split / juxtaposition
- Use color to encode the two sides

**Copy**:
- Parallel phrasing
- Let viewers take their own side — don't preach

### 3.4 Resonance + healing (`resonance_healing`)

**When to use**: a collective emotional moment (a beloved public figure's
kind gesture, a team's underdog win, a communal celebration)

**Visual recipe**:
- Warm palette
- Single-object or single-person close-ups
- Less grid, more breathing room

**Copy**:
- "you were all feeling it too"
- Lean into the shared reality; don't try to explain it

---

## 4. Mechanisms to avoid on this L1

- `blessing_ritual` — reads as opportunistic for events
- `utility_share` — extremely hard to pull off for news; mostly gets flagged
  as commercialization
- `regret_sting` — only appropriate for genuine loss; if used outside
  memorial contexts it reads exploitative

---

## 5. Category-specific taboos

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

## 6. Visual notes

- Don't use unlicensed photos of involved parties as hero frames;
  use illustration / abstracted imagery / type-driven cards
- Event footage: only use if public-domain / fair-use; our account does not
  host ripped material
- Typographic cards are often the strongest hook for this L1 because the
  audience needs context fast

---

## 7. Open questions

- [ ] Optimal card count for trending packs — is 50 still right, or should
      we ship shorter (30-35) for faster hit-rate?
- [ ] Do trending packs benefit from voiceover more than festival packs?
- [ ] How much does the decay curve differ by event type (awards vs sports
      vs pop culture)?

---

## 8. Historical experience (merged from `experience_log`, empty for now)

_Currently empty._

---

## Changelog

| Date | Version | Change |
|---|---|---|
| 2026-04-19 | v0.1 | Initial English draft |
