---
name: news-radar
description: Discover, normalize, cluster, preliminarily rank, and shortlist fresh news candidates for the Tin Nóng 5s V3 profile. Use before source verification. Never treat discovered URLs as verified final article links.
version: 3.0.0-package01
---

# M01 — NEWS RADAR

## 1. Mission

Find fresh, high-potential news candidates for a Vietnamese general-news Facebook workflow, prioritizing stories that can produce quality views, engagement, traffic, and monetization value.

M01 is a **discovery and prioritization module**, not a final source validator and not an editorial writer.

## 2. Required Inputs

- `RUN_CONTEXT`
- runtime category/source configuration
- optional previously observed story fingerprints/clusters
- approved public web/news search capability

Use `Asia/Ho_Chi_Minh` as the default Tin Nóng 5s operational timezone unless `RUN_CONTEXT.timezone` specifies otherwise.

## 3. Core Freshness Rule

Freshness is the highest-priority content gate.

### LIVE WINDOW

Default:

```text
run_at minus 2 hours → run_at
```

Prioritize stories first published or materially updated in this window.

### HOT WINDOW

Stories aged >2 hours and ≤24 hours by default may be considered only when there is a **verified new development today**.

Examples of acceptable new development:

- new official decision;
- new arrest/action/response;
- newly released figures;
- materially changed consequences;
- official confirmation of a previously developing event;
- significant next phase of an ongoing event.

A simple rewrite, repost, retrospective, or renewed social attention is not a new development.

### OLD NEWS

Do not shortlist old content merely because it is highly viral or interesting.

If an article/event is outside the permitted freshness model and has no new development today, mark:

```text
REJECTED_PRELIMINARY
```

with reason corresponding to old/stale news.

## 4. Tin Nóng 5s V3 Topic Priorities

Portfolio preference across runs:

1. **Money & Policy — 30%**
   - tax;
   - land;
   - benefits/support;
   - salaries/wages;
   - gold;
   - interest rates;
   - regulations/policies directly affecting citizens or businesses.

2. **Breaking / Social — 25%**
   - major breaking developments;
   - high-impact social events;
   - major official enforcement/action.

3. **Life Alert — 20%**
   - public safety;
   - consumer alerts;
   - weather/environment risks;
   - health/public-interest warnings when reliably sourced;
   - changes affecting daily life.

4. **Tech / Trend — 15%**
   - major AI/platform/technology changes;
   - technology events with broad public interest.

5. **Global / Sport / Entertainment — 10% combined**
   - include only when sufficiently important, viral, or relevant to Vietnamese audiences.

Do not force a category quota when no strong verified story exists.

## 5. Discovery Workflow

Live shadow discovery uses configured RSS/Atom adapters normalized into `Observation`.
Feed titles, summaries, times, and links are discovery evidence only and cannot establish
verification fields. Hybrid deduplication uses a normalized URL or explicit reliable
event key, never title equality alone.

### Step 1 — Establish run context

Read:

- `run_at`
- timezone
- LIVE WINDOW
- HOT WINDOW
- target brand profile

Never use a stale assumed current date/time.

### Step 2 — Search broadly but current-first

Search for candidate developments across relevant current-news sources and queries.

Prioritize:

- breaking/current reporting;
- official announcements;
- policy/economic developments;
- high public-impact news;
- stories emerging within the LIVE WINDOW.

### Step 3 — Normalize candidate metadata

For every candidate capture:

- observed headline;
- discovered URL;
- observed publisher;
- observed publication time if available;
- topic;
- key entities;
- concise factual summary;
- preliminary freshness bucket.

Do not invent missing metadata.

### Step 4 — Preliminary stale-content rejection

Preserve HOT, OLD, and unknown-time observations for M02 unless separate affirmative
evidence establishes that an item is archival/stale. A missing or false
`new_development_claimed` discovery hint is not proof of no development.

Set `preliminary_freshness.requires_m02_freshness_verification=true` for HOT,
OLD, and unknown observations. Only M02 may decide whether exact-article evidence
proves a current material development, proves no development, or remains unclear.

### Step 5 — Cluster duplicate coverage

Group reports about the same underlying event/development.

Do not fill the shortlist with five publishers reporting the same story.

Assign a common `story_cluster_id`.

Deterministic M01 duplicate rejection requires the same normalized article URL or
the same explicit reliable `event_key`. Equal or similar headlines on different URLs
are insufficient and both candidates must remain eligible for M02.

### Step 6 — Score each candidate

Score components from 0–100.

#### Viral Potential — 25% of Hot Score

Estimate natural likelihood of sharing/clicking/discussion based on the event itself, not clickbait wording.

#### Direct Life Impact — 25%

How directly does the story affect money, rights, travel, safety, work, housing, daily obligations, or practical decisions?

#### Money / Benefit Value — 20%

How strongly does it involve direct economic value, cost, benefits, taxes, wages, land/property, gold, rates, compensation, or financial consequences?

#### Emotional Pull — 15%

Measure legitimate emotional salience such as surprise, concern, curiosity, empathy, or urgency. Do not reward exploitative sensationalism.

#### Debate Potential — 10%

Likelihood of substantive public discussion or disagreement.

#### Freshness — 5%

Highest for truly recent developments within the LIVE WINDOW. This score cannot rescue stale content because stale content is already subject to hard gating.

Calculate:

```text
hot_score =
  0.25 * viral_potential
+ 0.25 * direct_life_impact
+ 0.20 * money_benefit_value
+ 0.15 * emotional_pull
+ 0.10 * debate_potential
+ 0.05 * freshness_score
```

Then score:

- `audience_quality_score`
- `money_value_score`
- `production_score`

Calculate:

```text
top_content_score =
  0.40 * hot_score
+ 0.30 * audience_quality_score
+ 0.20 * money_value_score
+ 0.10 * production_score
```

### Step 7 — Shortlist

Rank primarily by `top_content_score`, subject to:

- freshness;
- topic diversification;
- duplicate clustering;
- source plausibility;
- direct-life-impact priority.

**Hot Score is not identical to publish-now priority.** A shocking event with weak audience quality or monetization value may rank below a slightly less viral tax/land/public-policy story.

### Step 8 — Handoff to M02

Pass shortlisted candidates to Source Verifier.

Do not label a URL as `resolved_article_url` in M01.

## 6. URL Handling Rule

M01 may discover URLs from search results, publisher pages, or feeds, but they remain untrusted.

M01 must never claim that a link is the original verified article unless M02 validates it.

If the discovered URL is obviously a homepage/category/search URL, M01 may reject it early or pass it to M02 only when there is a realistic path to resolve the exact article.

## 7. Hard Prohibitions

M01 must not:

- include an old article as current merely because it is popular;
- fabricate a direct article link;
- fabricate timestamps;
- confuse article publication date with event date;
- duplicate one event across multiple shortlist positions;
- prioritize travel content by default;
- lower standards just to return a fixed number of stories;
- write Facebook captions;
- write first comments;
- write image-generation prompts;
- generate images;
- publish to Facebook.

## 8. Required Output

Return an array of `CANDIDATE_NEWS_PACKAGE` objects conforming to `DATA-CONTRACT.md`.

Each `news_id` is deterministic within one run and includes `run_id`; it changes when
the same URL appears in a later run. `story_cluster_id` remains a cross-source grouping
hint and does not replace M02 duplicate history.

Also return run-level summary:

```json
{
  "run_id": "...",
  "candidate_count": 0,
  "shortlisted_count": 0,
  "preliminary_rejected_count": 0,
  "shortlisted_news_ids": []
}
```

## 9. Human-Readable View

When a human-readable radar table is requested, use at minimum:

| Priority | Title | Hot Score | Viral Potential | Link status |
|---|---|---:|---:|---|

Before M02, `Link status` must indicate that the URL is not yet independently verified.

After M02, downstream presentation may use the exact `resolved_article_url`.

## 10. Final QA Checklist

Before returning M01 output, confirm:

- [ ] run time/timezone established;
- [ ] LIVE WINDOW applied;
- [ ] only affirmatively established archival/stale items are removed early;
- [ ] HOT/OLD/unknown observations needing exact-article freshness checks are preserved and marked;
- [ ] duplicate clusters created;
- [ ] no fabricated metadata;
- [ ] score formulas calculated correctly;
- [ ] Money & Policy/direct-impact preference reflected without forcing quotas;
- [ ] every shortlisted candidate is ready for independent M02 verification;
- [ ] no final verified-link claim has been made by M01.


## 11. Approved freshness clarification

M01 uses observed times only for preliminary ranking. Preserve the original
publication observation. A claimed substantive update/development may keep an
older article eligible for M02 inspection, but M01 cannot certify it.
M02 alone computes verified effective freshness, prioritizing material development,
then substantive update, then original publication time. Cosmetic updates,
recirculation, and rewriting never reset freshness. HOT requires new development
today and means >2 hours and ≤24 hours with the default runtime windows.

M01 must not interpret an absent/false discovery hint as verified absence. It marks
HOT, OLD, and unknown observations for M02 freshness verification. Headline equality
alone never causes preliminary duplicate rejection.
