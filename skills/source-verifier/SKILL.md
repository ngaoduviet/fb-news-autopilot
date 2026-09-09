---
name: source-verifier
description: Independently validate shortlisted news candidates by resolving the exact article URL, confirming source, article type, publication time, event timing, freshness, factual support, and duplicate status. Required gate before editorial generation.
version: 1.0.0
---

# M02 — SOURCE VERIFIER

## 1. Mission

Convert an M01 candidate into a **verified, traceable news source package** or reject/review it with deterministic reasons.

M02 exists specifically to prevent:

- old news entering current-news output;
- homepage/category/search links being presented as article links;
- incorrect or invented origin URLs;
- headlines unsupported by source content;
- duplicate event coverage being treated as different news.

## 2. Required Input

One `CANDIDATE_NEWS_PACKAGE` plus its `RUN_CONTEXT`.

M02 must independently inspect the source. Do not accept M01 observations as final verification.

## 3. Verification Workflow

### Step 1 — Validate URL syntax

The candidate must have a syntactically valid HTTP(S) URL.

Otherwise:

```text
REJECT_INVALID_URL
```

### Step 2 — Resolve destination

Follow normal redirects and record:

- `discovered_url`
- final/resolved URL
- canonical URL when available

Do not silently replace a failed link with an unrelated publisher homepage.

### Step 3 — Classify page type

Classify the resolved page as:

- ARTICLE
- HOMEPAGE
- CATEGORY
- TAG_TOPIC
- SEARCH_RESULTS
- AGGREGATOR
- REDIRECT_ONLY
- INACCESSIBLE
- UNKNOWN

Only `ARTICLE` may become the final verified source page.

Reject invalid final page classes with the matching rejection code.

### Step 4 — Verify publisher/source identity

Confirm that the article belongs to the stated publisher or official source.

Prefer an origin/primary source where it materially improves factual accuracy, but preserve reputable corroboration.

If identity cannot be established:

```text
REVIEW_SOURCE_IDENTITY_UNCLEAR
```

or reject when clearly unreliable/unverifiable.

### Step 5 — Verify article publication time

Extract/confirm the article publication timestamp from reliable page metadata/text.

Normalize to ISO 8601 with timezone.

If timezone is omitted but publisher-local timezone can be reliably established, normalize accordingly and record confidence.

If publication time cannot be established well enough to enforce freshness:

```text
REVIEW_PUBLICATION_TIME_UNCLEAR
```

Never guess.

### Step 6 — Verify event time / new-development time

Determine when the underlying event or material new development occurred when this matters to the current-news claim.

Distinguish:

- article publish time;
- event time;
- update time;
- date of an older background event.

If event timing is materially ambiguous:

```text
REVIEW_EVENT_TIME_UNCLEAR
```

### Step 7 — Apply freshness gate

#### LIVE

If publication/development is within the default 2-hour LIVE WINDOW and no contrary evidence exists, continue.

#### HOT

If older than 2 hours but within 24 hours, verify a materially new development today.

Store the evidence basis in `freshness_basis`.

If no genuine new development exists:

```text
REJECT_NO_NEW_DEVELOPMENT
```

If outside the permitted window:

```text
REJECT_OLD_NEWS
```

### Step 8 — Verify headline support

The candidate title/claim must be materially supported by the exact source article.

Reject when the headline changes:

- proposal → approved decision;
- allegation → proven fact;
- possibility → certainty;
- old event → current event;
- partial/local case → universal rule;
- forecast → actual event.

Use:

```text
REJECT_HEADLINE_UNSUPPORTED
```

### Step 9 — Verify factual summary

Every key fact passed forward must be supported by the source or clearly identified corroborating source.

If material facts are unsupported:

```text
REJECT_FACTS_UNSUPPORTED
```

### Step 10 — Duplicate check

Compare:

- canonical URL;
- story cluster;
- key entities;
- event/development;
- previously accepted candidates available to the run.

If materially the same story/development has already been selected:

```text
REJECT_DUPLICATE_STORY
```

Do not reject a genuinely new development in an ongoing story merely because the broader topic appeared earlier.

### Step 11 — Make decision

#### VERIFIED

Use only when:

- exact article URL verified;
- source/publisher sufficiently verified;
- publication freshness verified;
- event/new-development timing sufficiently verified where material;
- headline supported;
- core facts supported;
- not duplicate.

#### REVIEW

Use when evidence is potentially valid but a material verification item remains ambiguous.

`REVIEW` is not eligible for automatic editorial/publishing handoff.

#### REJECTED

Use for hard failures.

## 4. Direct Article Link Standard

A valid final link must open the exact detailed article that supports the news candidate.

### Automatically invalid as final source

- `https://publisher.vn/`
- `https://publisher.vn/kinh-te/`
- `https://publisher.vn/tim-kiem?...`
- topic/tag collection pages;
- generic news portal landing page;
- search-engine result;
- social post linking elsewhere when a direct article exists.

The human-readable `Link báo gốc` downstream must use `resolved_article_url` from a `VERIFIED` M02 result.

## 5. Accessibility Rule

A source must expose enough article content/metadata to verify the factual claim.

If the URL exists but only an inaccessible shell/paywall/blocked page prevents meaningful verification, do not claim verification from the URL alone.

Return `REVIEW` or `REJECTED` according to whether independent reliable verification can satisfy the same origin claim.

## 6. Freshness Examples

### Example A — reject old article

```text
run_at: 2026-09-09 05:00 +07
article publication: 2026-07-17
no new development today
```

Decision:

```text
REJECTED
REJECT_OLD_NEWS
```

### Example B — article from yesterday with new development today

```text
original event: yesterday
new official decision: today at 04:20
current article reports that new decision
run_at: 05:00
```

Potential decision:

```text
VERIFIED / LIVE
```

provided all other checks pass.

### Example C — recirculated viral story

```text
old event
new social shares today
no factual development today
```

Decision:

```text
REJECTED
REJECT_NO_NEW_DEVELOPMENT
```

## 7. Required Output

On VERIFIED, return `VERIFIED_NEWS_PACKAGE` conforming to `DATA-CONTRACT.md`.

On REVIEW/REJECTED, return the same traceable identification fields plus:

```json
{
  "verification": {
    "status": "REJECTED",
    "resolved_article_url": null,
    "rejection_codes": ["REJECT_OLD_NEWS"],
    "review_codes": [],
    "evidence_summary": "..."
  },
  "handoff": {
    "eligible_for_editorial_module": false,
    "package_01_complete": true
  }
}
```

## 8. Hard Prohibitions

M02 must never:

- fabricate an article URL;
- replace an invalid source with a homepage and still mark VERIFIED;
- infer freshness from search-result ordering alone;
- use virality to override stale-news rejection;
- use article publish time as proof the underlying event is new when the article is merely retrospective;
- change “proposal” into “approved” or similar fact level;
- auto-pass REVIEW cases;
- write Facebook captions, image prompts, or posts.

## 9. Final QA Checklist

Before `VERIFIED`:

- [ ] resolved URL opens exact article;
- [ ] page type is ARTICLE;
- [ ] publisher/source identity verified;
- [ ] publication time verified;
- [ ] event/new-development time checked where material;
- [ ] LIVE/HOT/OLD bucket justified;
- [ ] HOT candidate has genuine new development today;
- [ ] headline supported;
- [ ] core facts supported;
- [ ] duplicate check passed;
- [ ] rejection/review arrays empty;
- [ ] `eligible_for_editorial_module=true` only for VERIFIED.
