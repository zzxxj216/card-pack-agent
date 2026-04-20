# Global Style Guide

Loaded into every agent's system prompt. Covers general aesthetics and
narrative principles. Category-specific differences live in `categories/*.md`.

**Audience**: English-speaking TikTok viewers (US / CA / UK / AU primary;
global English secondary). All overlay copy, tone descriptors, and
narrative notes produced by agents must be in English.

---

## 1. Visual consistency

### 1.1 Within a single pack
- Main palette: at most 2 color families per pack (one accent color is fine)
- Typography: at most 2 headline faces per pack, one body face
- Composition rhythm: hook cards (1-3 or 1-5) may break rhythm; all other
  cards should keep the visual cadence

### 1.2 Across packs (account identity)
- Type family: `serif` for narrative packs / `sans-display` for emotional packs
  as primary options
- Logo / watermark: bottom-right, 8pt, must not cover the subject
- Canvas: locked at 9:16 (1080x1920)

---

## 2. Typography

### 2.1 Size tiers (vertical 1080x1920 canvas)
| Use | Size (pt) | Leading |
|---|---|---|
| Mega hook | 80-120 | 1.0 |
| Title | 48-72 | 1.1 |
| Body | 28-40 | 1.3 |
| Caption | 20-24 | 1.4 |

### 2.2 Hard rules
- Max overlay copy per card: ~ 12 English words (hook may stretch to 14)
- Copy must not sit on faces, hands, or any visual focal point
- Contrast ratio >= 4.5:1 against background (WCAG AA)
- Avoid "center-aligned + long copy" — it diffuses focus

---

## 3. Narrative pacing

### 3.1 Golden structure for a 50-card pack

```
[ 1-3  ]  Hook cards: pose a question / prick a pain / flip an expectation
[ 4-8  ]  Setup 1: plant emotion or scene
[ 9-20 ]  Setup 2: concrete detail / evidence / scene shifts
[21-35 ]  Peak: core claim / deepest emotion / strongest visual
[36-45 ]  Turn / reflect / deepen
[46-50 ]  Close: resolve / CTA / silence
```

Card counts are not fixed. Short packs (20-30) or long packs (80+) scale
proportionally.

### 3.2 Negative space
- At least 20% of cards should be "breathing" cards: less copy, slower beat,
  visual breathing room
- Do not punch an opinion on all 50 cards; viewers fatigue fast

### 3.3 Hook intensity
Hook cards must satisfy **at least one** of:
- Counter-intuitive: overturns a common expectation
- Emotional prick: hits a universal regret / pain
- Visual impact: single strong image + large type
- Suspense: "what if..." / "if it weren't for..."

---

## 4. Copy voice

### 4.1 Tone
- Close but not sycophantic: talk like a friend, not an auntie
- Restrained but not cold: feel the feeling; don't wallow
- Concrete beats abstract: "the bowl of soup she left cold" > "the taste of
  longing"

### 4.2 Person
- Prefer second person "you" over "we"
- Avoid overusing "I" unless the card genuinely requires a first-person voice
- Never address the audience as "guys" or "besties" by default (reads
  performative on short-form without context)

### 4.3 Overused fillers / stale phrasings (avoid)
- "In this fast-paced world..."
- "We've all been there..."
- "Have you ever had that moment where..." (saturated)
- "Sending love to everyone who..."
- Standalone "real", "literally", "no cap" as hype intensifiers
- Blessing-style openers "May you..." outside of `blessing_ritual` packs

---

## 5. The "too much" line for emotion

One-liner: **feel one notch more than the viewer; don't feel three notches
more.**

Over-emotion signals (Evaluator should warn):
- Multiple consecutive cards using "crying", "tears", "sobbing", "devastated",
  "wrecked", "broken"
- Over-personalization: "girlies I'm literally..."
- Forced uplift at the end: "and that's just life"

---

## 6. CTA usage

| Mechanism | CTA intensity | Example |
|---|---|---|
| `resonance_healing` | `soft` | "ever had a night like this?" |
| `regret_sting` | `none` / `soft` | silence, or "tell me in the comments" |
| `contrast_twist` | `soft` | "the last card hit different" |
| `blessing_ritual` | `soft` | "send this to someone who needs it" |
| `utility_share` | `hard` | "save this / share with them" |
| `aphorism_lesson` | `soft` | "agree? drop a 1" |
| `conflict_tension` | `none` | leave silence; let viewers argue |

---

## 7. AI image generation — baseline

- Every prompt must include a style anchor
  (e.g. `film photography, 35mm, natural light`)
- Negative prompt must include text-related tokens:
  `text, watermark, logo, typography, captions, lettering` — overlay text is
  composited in post, never generated inside the image
- All cards in one pack should share a seed family or a single style
  reference image
- Human-subject generation requires a post-check: finger count, facial
  symmetry, eye direction

---

## Changelog

| Date | Version | Change |
|---|---|---|
| 2026-04-17 | v0.1 | Initial CN version |
| 2026-04-19 | v0.2 | Full English rewrite; audience shifted to overseas TikTok |
