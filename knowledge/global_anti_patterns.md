# Global Anti-Patterns — Hard constraints

**Highest-priority document.** Loaded by Planner, Generator, and Evaluator.
Triggering any hard rule here = immediate FAIL. No human-review override on
hard-fail items; warn items get a nudge but don't block publishing.

---

## 1. Platform compliance (TikTok Community Guidelines mapping)

### 1.1 Absolutely prohibited (risk = account ban)
- Explicit depiction or method description of self-harm or suicide
- Minors in sexualized, suggestive, or intimate-with-adult contexts
- Hate speech: slurs or dehumanizing claims targeting race, ethnicity,
  religion, national origin, sexual orientation, gender identity, disability,
  caste, immigration status, or serious disease
- Terrorist / violent extremist organization symbols or propaganda
- Illegal goods promotion (controlled substances, weapons, wildlife, pirated
  goods)
- Graphic gore, corpses, or content intended to shock / disgust

### 1.2 High risk (likely limited reach or takedown)
- Explicit medical claims or treatment recommendations ("this cures...")
- Specific financial advice ("buy / sell / hold X")
- Unlicensed celebrity likeness used in a commercial context
- Third-party brand logos appearing prominently (unless we are the brand)
- Partisan political stances on elections / officeholders
- Vaccine or public-health stance-taking (both directions)
- Dangerous stunts without warnings (extreme sports, self-harming challenges,
  unsafe food consumption)

---

## 2. Copyright

- No verbatim copyrighted lyrics, poetry, or prose
- No direct replication of another creator's card-pack visual + copy
  structure (mechanisms may be borrowed; specific frames may not)
- AI image generation must not imitate a living artist's distinctive
  individual style; public-domain styles are fine
- No use of real people's photographs unless explicitly licensed, public
  domain, or newsworthy use under fair-use limits

---

## 3. Festival / holiday category — specific taboos

### 3.1 Stance avoidance on sensitive dates

Do not take or imply a stance on these dates; default to neutral-respectful
or skip the topic entirely:

- **September 11 (Patriot Day, US)** — no humor, no "reversal" mechanic
- **Holocaust Remembrance Day (Jan 27 intl., Yom HaShoah)** — no dramatization
- **Martin Luther King Jr. Day (US, 3rd Mon Jan)** — respect-required, no
  brand-opportunistic CTAs
- **Juneteenth (US, Jun 19)** — celebratory is fine; do not commercialize or
  use as a generic summer-kickoff hook
- **Memorial Day (US, last Mon May)** — somber framing only; never a "start
  of summer" sale pitch
- **Veterans Day (US, Nov 11) / Remembrance Day (UK/CA/AU/NZ, Nov 11)** —
  respectful framing only
- **Indigenous Peoples' Day / Thanksgiving (US, 4th Thu Nov)** —
  acknowledge complexity; do not glorify colonial framings
- **National days of mourning / major tragedies in any country** (school
  shootings, natural disasters, public figure deaths) — skip unless
  explicitly producing condolence content
- **Religious observances** (Ramadan / Eid, Yom Kippur, Good Friday,
  Vesak, Diwali, Hanukkah, etc.) — celebrate respectfully; do not
  mock, parody, or frame one tradition as "better" than another

### 3.2 Stereotyped narratives to avoid

- "Whole family reunited" as the default family shape (erases single,
  divorced, childfree, estranged, LGBTQ+, long-distance, immigrant-separated
  audiences)
- Mother's Day = praising only sacrifice / selfless suffering (reinforces
  gendered-labor stereotypes)
- Valentine's Day defaulting to heterosexual coupling
- Father's Day leaning on "breadwinner / stoic provider" as the only
  archetype
- Christmas / New Year centering Western/Christian iconography as
  universal (remember the audience includes non-Christian viewers)

### 3.3 Commercial boundaries
- Gift-guide (`utility_share`) content is fine, but do not imply "not gifting
  = not loving"
- No emotional-blackmail CTAs like "if you don't share this, you don't care"

---

## 4. Copy

### 4.1 Direct banned-word regex
Platform-sensitive terms tracked in
`knowledge/_lexicon/banned_words.txt` (loaded by Evaluator). Includes at
least:
- Direct self-harm / suicide phrases
- Sexual content direct phrases
- Slurs / hate speech terms
- Brand-blacklist (competitors, partners who require shielding)

### 4.2 Structural issues
- Over-saturation of emotion: 3+ consecutive cards using "crying", "tears",
  "sobbing", "broken", "wrecked" = flagged as over-emotion
- Social blackmail: "share this if you're a real [X]", "must like"
- False promises: "watch this to guarantee X", "lose 10 lb in 3 days"
- Stale memes (review quarterly): overuse of `no cap`, `slay queen`,
  `it's giving`, `main character energy`, `living rent free`,
  `understood the assignment`, `ate and left no crumbs`

---

## 5. Visual

- Uncanny-valley AI people: extra fingers, facial distortion, mismatched eyes
  — must reshoot
- Broken AI-generated typography inside the image: all overlay text is
  composited in post; never rely on AI models to render text inside the image
- More than 3 near-duplicate cards (same scene, composition, subject) in
  one pack = rework
- Subject occluded by watermark or platform logo

---

## 6. Brand red lines (account-specific, ops to fill)

> **Ops team fills this section.** Template:
>
> - Brand colors strictly limited to `#XXXXXX` / `#YYYYYY`
> - Competitors to exclude: [TBD]
> - This account does not run paid promotions (promos go on sub-account)
> - All human figures must read as 18+

---

## 7. Evaluator checklist (machine-executable)

```yaml
hard_fail:
  - banned_word_detected
  - explicit_self_harm_reference
  - unauthorized_celebrity_face
  - watermark_over_subject
  - text_corruption_in_generated_image
  - card_visual_duplication > 3
  - brand_red_line_violation

warn:
  - excessive_emotional_keywords   # hype-word run > 3 cards
  - stale_meme_detected
  - overclaim_phrasing             # "must", "guaranteed", "100%"
  - stereotype_family_narrative    # festival-specific
```

---

## Changelog

| Date | Version | Change |
|---|---|---|
| 2026-04-17 | v0.1 | Initial CN version (platform, copyright, festival, copy, visual) |
| 2026-04-19 | v0.2 | English rewrite; sensitive-dates list swapped to international (TikTok US / global) |
