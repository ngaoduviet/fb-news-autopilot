# FB NEWS AUTOPILOT — PACKAGE 01 DATA CONTRACT

## 1. Purpose

This contract defines the structured objects exchanged between the trigger, M01 News Radar, M02 Source Verifier, and future modules.

All timestamps MUST use ISO 8601 with timezone offset.

Example:

```text
2026-09-09T05:00:00+07:00
```

## 2. Common Conventions

- Score range: integer or decimal `0–100`.
- URLs: fully qualified `https://...` URLs.
- Unknown values: `null`, never fabricated placeholders.
- Arrays: use `[]`, not null, unless schema explicitly permits null.
- Status values: use enumerations defined below.
- Evidence fields: concise factual basis, not speculative reasoning.

## 3. RUN_CONTEXT

```json
{
  "run_id": "TN5S-20260909T050000+0700",
  "run_at": "2026-09-09T05:00:00+07:00",
  "timezone": "Asia/Ho_Chi_Minh",
  "live_window_hours": 2,
  "hot_window_hours": 24,
  "brand_profile": "tin_nong_5s_v3",
  "mode": "shadow"
}
```

### `mode` enum

- `shadow`
- `approval`
- `production`

Package 01 itself never publishes regardless of mode.

## 4. CANDIDATE_NEWS_PACKAGE — M01 Output

```json
{
  "news_id": "TN5S-20260909-001",
  "story_cluster_id": "cluster-...",
  "discovery": {
    "query_or_feed": "...",
    "discovered_at": "2026-09-09T05:03:12+07:00",
    "discovered_url": "https://publisher.example/article",
    "publisher_name": "...",
    "headline_observed": "...",
    "publication_time_observed": "2026-09-09T04:40:00+07:00"
  },
  "normalized": {
    "title": "...",
    "topic": "money_policy",
    "summary_facts": [
      "fact 1",
      "fact 2"
    ],
    "main_entities": ["..."],
    "location": "..."
  },
  "scores": {
    "viral_potential": 0,
    "direct_life_impact": 0,
    "money_benefit_value": 0,
    "emotional_pull": 0,
    "debate_potential": 0,
    "freshness_score": 0,
    "hot_score": 0,
    "audience_quality_score": 0,
    "money_value_score": 0,
    "production_score": 0,
    "top_content_score": 0
  },
  "preliminary_freshness": {
    "bucket": "LIVE",
    "age_hours": 0.4,
    "new_development_claimed": false,
    "requires_m02_freshness_verification": false
  },
  "m01_status": "SHORTLISTED"
}
```

### `topic` enum — initial Tin Nóng 5s profile

- `money_policy`
- `breaking_social`
- `life_alert`
- `tech_trend`
- `global`
- `sport`
- `entertainment`
- `other`

### `preliminary_freshness.bucket` enum

- `LIVE`
- `HOT`
- `OLD`
- `UNKNOWN`

### `m01_status` enum

- `DISCOVERED`
- `SHORTLISTED`
- `REJECTED_PRELIMINARY`

M01 may perform obvious preliminary rejection, but M02 owns the final verification decision.

`preliminary_freshness.requires_m02_freshness_verification` is `true` whenever
the observed publication time is HOT, OLD, or unknown and M02 must inspect the exact
article to establish effective freshness. A missing or false
`new_development_claimed` value is an observation, not verified proof that no new
development exists, and cannot by itself cause M01 rejection.

M01 duplicate rejection requires either an identical normalized article URL or an
identical explicit reliable event key. Equal or similar headlines alone are never
sufficient.

## 5. SOURCE_VERIFICATION — M02 Output Block

The unified verification block (the additional source and freshness fields live
in their dedicated top-level objects):

```json
{
  "verification": {
    "status": "VERIFIED",
    "verified_at": "2026-09-09T05:06:00+07:00",
    "page_type": "ARTICLE",
    "article_accessible": true,
    "headline_supported": true,
    "facts_supported": true,
    "origin_quality": "DIRECT_REPUTABLE_ARTICLE",
    "rejection_codes": [],
    "review_codes": [],
    "evidence_summary": "The exact article supports the headline and all summary facts."
  }
}
```

### `verification.status` enum

- `VERIFIED`
- `REVIEW`
- `REJECTED`

### `page_type` enum

- `ARTICLE`
- `HOMEPAGE`
- `CATEGORY`
- `TAG_TOPIC`
- `SEARCH_RESULTS`
- `AGGREGATOR`
- `REDIRECT_ONLY`
- `INACCESSIBLE`
- `UNKNOWN`

Only `ARTICLE` can be `VERIFIED` as the final source page.

### Confidence enum

- `HIGH`
- `MEDIUM`
- `LOW`
- `UNKNOWN`

### `origin_quality` initial enum

- `PRIMARY_OFFICIAL`
- `DIRECT_REPUTABLE_ARTICLE`
- `SECONDARY_REPUTABLE_ARTICLE`
- `AGGREGATOR_ONLY`
- `UNKNOWN`

## 6. REJECTION CODES

Hard rejection codes:

- `REJECT_OLD_NEWS`
- `REJECT_NO_NEW_DEVELOPMENT`
- `REJECT_NOT_DIRECT_ARTICLE`
- `REJECT_HOMEPAGE_URL`
- `REJECT_CATEGORY_URL`
- `REJECT_SEARCH_URL`
- `REJECT_TAG_TOPIC_URL`
- `REJECT_AGGREGATOR_AS_FINAL_SOURCE`
- `REJECT_REDIRECT_TO_NON_ARTICLE`
- `REJECT_ARTICLE_INACCESSIBLE`
- `REJECT_SOURCE_UNVERIFIABLE`
- `REJECT_HEADLINE_UNSUPPORTED`
- `REJECT_FACTS_UNSUPPORTED`
- `REJECT_DUPLICATE_STORY`
- `REJECT_INVALID_URL`

## 7. REVIEW CODES

Non-pass states requiring manual or later resolution:

- `REVIEW_PUBLICATION_TIME_UNCLEAR`
- `REVIEW_EVENT_TIME_UNCLEAR`
- `REVIEW_SOURCE_IDENTITY_UNCLEAR`
- `REVIEW_NEW_DEVELOPMENT_UNCLEAR`
- `REVIEW_CONFLICTING_SOURCES`
- `REVIEW_DUPLICATE_UNCERTAIN`
- `REVIEW_ARTICLE_ACCESS_LIMITED_CORROBORATED`
- `REVIEW_HEADLINE_SUPPORT_UNCLEAR`
- `REVIEW_FACT_SUPPORT_UNCLEAR`

A candidate in `REVIEW` must not be automatically passed to a future auto-publishing path.

## 8. PACKAGE_01_RESULT — Unified Terminal Object

The example below illustrates VERIFIED. All terminal statuses use these same top-level fields, as defined in §11. VERIFIED_NEWS_PACKAGE is the VERIFIED-only subset.

```json
{
  "schema_version": "1.0.0",
  "run_context": {
    "run_id": "TN5S-20260909T050000+0700",
    "run_at": "2026-09-09T05:00:00+07:00",
    "timezone": "Asia/Ho_Chi_Minh",
    "live_window_hours": 2,
    "hot_window_hours": 24,
    "brand_profile": "tin_nong_5s_v3",
    "mode": "shadow"
  },
  "news_id": "TN5S-20260909-001",
  "story_cluster_id": "cluster-...",
  "source": {
    "publisher_name": "Example Publisher",
    "discovered_url": "https://publisher.example/exact-article",
    "resolved_article_url": "https://publisher.example/exact-article",
    "canonical_url": "https://publisher.example/exact-article",
    "publication_time": "2026-09-09T04:40:00+07:00",
    "last_updated_time": null,
    "event_time": "2026-09-09T03:55:00+07:00",
    "material_development_time": null,
    "corroborating_urls": []
  },
  "content": {
    "candidate_title": "Example factual headline",
    "candidate_summary_facts": [
      "Example fact"
    ],
    "main_entities": [],
    "topic": "money_policy",
    "location": null,
    "verified_title": "Example factual headline",
    "verified_summary_facts": [
      "Example fact"
    ]
  },
  "freshness": {
    "bucket": "LIVE",
    "age_hours": 0.3333333333333333,
    "effective_freshness_time": "2026-09-09T04:40:00+07:00",
    "basis": "Article publication is within the LIVE window, with no contrary event evidence."
  },
  "scores": {
    "viral_potential": 0,
    "direct_life_impact": 0,
    "money_benefit_value": 0,
    "emotional_pull": 0,
    "debate_potential": 0,
    "freshness_score": 0,
    "hot_score": 0,
    "audience_quality_score": 0,
    "money_value_score": 0,
    "production_score": 0,
    "top_content_score": 0
  },
  "verification": {
    "status": "VERIFIED",
    "verified_at": "2026-09-09T05:06:00+07:00",
    "page_type": "ARTICLE",
    "article_accessible": true,
    "headline_supported": true,
    "facts_supported": true,
    "origin_quality": "DIRECT_REPUTABLE_ARTICLE",
    "rejection_codes": [],
    "review_codes": [],
    "evidence_summary": "The exact article supports the headline and all summary facts."
  },
  "handoff": {
    "eligible_for_editorial_module": true,
    "package_01_complete": true
  }
}
```

## 9. M01 Score Calculations

### Hot Score

```text
hot_score =
  0.25 * viral_potential
+ 0.25 * direct_life_impact
+ 0.20 * money_benefit_value
+ 0.15 * emotional_pull
+ 0.10 * debate_potential
+ 0.05 * freshness_score
```

### Top Content Score

```text
top_content_score =
  0.40 * hot_score
+ 0.30 * audience_quality_score
+ 0.20 * money_value_score
+ 0.10 * production_score
```

Round only for display. Preserve sufficient precision internally.

## 10. Human-Readable Radar View

A user-facing view may be generated from the structured object, but is not the inter-module contract.

Minimum recommended columns:

| Priority | Title | Hot Score | Viral Potential | Direct Article Link |
|---|---|---:|---:|---|

The displayed link MUST be `resolved_article_url` for verified stories—not the original search/category/homepage link.


## 11. Approved Package 01 clarification (authoritative)

The following approved decisions supersede earlier examples wherever they differ.

### 1. FRESHNESS DECISION

==================================================

Freshness must be based on the latest VERIFIED MATERIAL DEVELOPMENT,
not blindly on the original article publication timestamp.

Add/normalize these time concepts:

- publication_time:
  original article publication time.

- last_updated_time:
  latest visible article update timestamp, nullable.

- material_development_time:
  timestamp of the newest substantive factual development,
  nullable.

- effective_freshness_time:
  the timestamp actually used to determine LIVE / HOT / OLD.

Rules:

A. Default LIVE:
   effective_freshness_time is within 0–2 hours before run_at.

B. Default HOT:
   effective_freshness_time is >2 hours and <=24 hours before run_at.

C. OLD:
   effective_freshness_time is >24 hours before run_at.

D. An article originally published more than 24 hours ago MAY still become
   LIVE or HOT ONLY IF the exact article currently being verified contains
   and supports a genuinely material new development, or a substantive
   article update, whose verified time falls inside the LIVE/HOT window.

Example:

publication_time = 2 days ago
material_development_time = 45 minutes ago
exact article contains and substantiates that new development

=> freshness = LIVE

E. A cosmetic "updated" timestamp is NOT enough.
   The update must contain a materially new factual development.

F. If an article is >24 hours old and the old article itself does NOT contain
   or substantiate the new development, it cannot be used as the verified
   source merely because another source reports something new.

In that case:
- reject the old article for the current-news claim; and
- the genuinely current direct article/source must be discovered and verified
  as a separate candidate/source.

G. Social recirculation, renewed virality, rewrite/republication without a
   substantive factual development do NOT reset freshness.

H. Normalize all Package 01 wording so HOT means:

   >2 hours and <=24 hours

Replace any ambiguous wording such as "within 12–24 hours".

Freshness precedence:

1. verified material_development_time
2. verified substantive last_updated_time
3. publication_time

Never use search result ordering as freshness evidence.

==================================================
2. UNIFIED SCHEMA FOR VERIFIED / REVIEW / REJECTED
==================================================

Use ONE traceable PACKAGE 01 result object shape for all terminal statuses.

The following top-level fields must always exist:

- schema_version
- run_context
- news_id
- story_cluster_id
- source
- content
- freshness
- scores
- verification
- handoff

Preserve M01 evidence even when M02 returns REVIEW or REJECTED.

SOURCE fields:

Required:
- publisher_name
- discovered_url

Nullable when not established:
- resolved_article_url
- canonical_url
- publication_time
- last_updated_time
- event_time
- material_development_time

Always preserve:
- corroborating_urls []

CONTENT:

Preserve original candidate information separately from verified information.

Required candidate/audit fields:
- candidate_title
- candidate_summary_facts []
- main_entities []
- topic
- location

Verified fields:
- verified_title: string | null
- verified_summary_facts: array

Do not label unverified candidate text as "verified".

FRESHNESS:

- bucket: LIVE | HOT | OLD | UNKNOWN
- age_hours: number | null
- effective_freshness_time: datetime | null
- basis: string

SCORES:

Preserve all M01 scores in REVIEW and REJECTED results for auditability.
Scores must never override an M02 verification failure.

VERIFICATION required fields:

- status: VERIFIED | REVIEW | REJECTED
- verified_at
- page_type
- article_accessible
- headline_supported
- facts_supported
- origin_quality
- rejection_codes []
- review_codes []
- evidence_summary

Use tri-state values where appropriate:

headline_supported:
  true | false | null

facts_supported:
  true | false | null

article_accessible:
  true | false | null

STATUS constraints:

VERIFIED:
- rejection_codes must be []
- review_codes must be []
- resolved_article_url must be non-null
- page_type must be ARTICLE
- headline_supported = true
- facts_supported = true
- eligible_for_editorial_module = true

REVIEW:
- at least one review_code required
- rejection_codes = []
- eligible_for_editorial_module = false

REJECTED:
- at least one rejection_code required
- eligible_for_editorial_module = false
- review_codes should normally be [] because the hard rejection is terminal

HANDOFF:

For VERIFIED:
- eligible_for_editorial_module = true
- package_01_complete = true

For REVIEW:
- eligible_for_editorial_module = false
- package_01_complete = true

For REJECTED:
- eligible_for_editorial_module = false
- package_01_complete = true

Unknown values must be null.
Never fabricate placeholders.

==================================================
3. PAYWALL / BLOCKED / INACCESSIBLE ARTICLE
==================================================

A paywalled or technically blocked source must NOT automatically become
VERIFIED merely because its URL exists.

Add this review code:

REVIEW_ARTICLE_ACCESS_LIMITED_CORROBORATED

Decision logic:

A. Exact article is inaccessible/partially inaccessible,
   BUT article identity and the same substantive claim can be independently
   corroborated by reliable sources:

=> status = REVIEW
=> review_codes =
   ["REVIEW_ARTICLE_ACCESS_LIMITED_CORROBORATED"]

Store the corroborating direct article URLs in corroborating_urls.

This state is NOT eligible for automatic editorial/publishing handoff.

B. Exact article is inaccessible AND independent reliable evidence cannot
   sufficiently verify the same claim:

=> status = REJECTED
=> use:
   REJECT_ARTICLE_INACCESSIBLE

and/or, where appropriate:

   REJECT_SOURCE_UNVERIFIABLE

C. Never mark a paywalled/blocked article VERIFIED only from:
- search snippet
- headline snippet
- URL existence
- aggregator excerpt

D. If another fully accessible reputable direct article independently reports
the same current development, that article should enter the normal verification
process as its own valid source/candidate rather than silently converting the
blocked article to VERIFIED.

==================================================
4. SEMANTIC SUPPORT IS UNCLEAR
==================================================

Do NOT treat "unclear" as "unsupported".

Add these review codes:

- REVIEW_HEADLINE_SUPPORT_UNCLEAR
- REVIEW_FACT_SUPPORT_UNCLEAR

Decision logic:

A. Evidence clearly contradicts or materially fails the headline:
=> REJECT_HEADLINE_UNSUPPORTED

Examples:
proposal -> falsely reported as approved
allegation -> falsely reported as proven
forecast -> falsely reported as actual event

B. Evidence clearly fails a material fact:
=> REJECT_FACTS_UNSUPPORTED

C. Available evidence is ambiguous or insufficient to determine whether
headline support is true or false:
=> REVIEW
=> REVIEW_HEADLINE_SUPPORT_UNCLEAR
=> headline_supported = null

D. Available evidence is ambiguous or insufficient to determine whether
a material fact is supported:
=> REVIEW
=> REVIEW_FACT_SUPPORT_UNCLEAR
=> facts_supported = null

REVIEW is never eligible for automatic editorial/publishing handoff.

==================================================
5. DUPLICATE TEST CODE
==================================================

Use the canonical code already defined by DATA-CONTRACT.md:

REJECT_DUPLICATE_STORY

Do NOT create REJECT_DUPLICATE.



## 12. Schema and audit implementation mapping

Checked-in schemas use JSON Schema Draft 2020-12:

- `run-context.schema.json`: RUN_CONTEXT.
- `candidate-news-package.schema.json`: CANDIDATE_NEWS_PACKAGE; prohibits M02 fields.
- `source-verification.schema.json`: unified verification block.
- `package-01-result.schema.json`: unified terminal result, with status/handoff constraints.
- `verified-news-package.schema.json`: VERIFIED-only subset.
- `radar-summary.schema.json`: M01 run summary.
- `run-result.schema.json`: run outcome, candidates, terminal results and audit events.

M01 inter-module candidate URLs obey the HTTPS convention. Raw invalid URL
submissions are ingress errors, retained verbatim in the external raw-observation
audit. A direct M02 invalid-URL submission also retains the original raw string in
terminal `source.discovered_url`; it cannot reach VERIFIED. This audit-only exception
allows the required REJECT_INVALID_URL case to be recorded without fabricating a URL.

Unmodified observations, complete fetched HTML, extracted article evidence, unused
raw timestamps and final redirect destination are retained in a separate append-only
run evidence bundle. The terminal result is not the sole evidence store.
Unknown publication/update/event metadata remains null; the raw value, if malformed,
is retained in evidence. Schemas enforce structural rules; Python enforces relative
time, timezone, freshness evidence, weights and duplicate rules.

## 13. Approved Acceptance Fix Round 1 rules

### Direct article classification

Configured category paths, homepage, search, tag/topic, and configured aggregator
classification take precedence over generic article signals. A generic HTML
`<article>` element alone is insufficient. ARTICLE requires stronger evidence such
as article structured data, `og:type=article`, or an explicit publisher article rule.

### Duplicate identity

Duplicate history retains normalized URL, nullable verified event key, and effective
freshness time. The decision table is:

- same non-null verified event key: duplicate, regardless of URL;
- same URL and same non-null verified event key: duplicate;
- same URL and different non-null verified event keys: new material phase;
- same URL with unresolved event identity: `REVIEW_DUPLICATE_UNCERTAIN`.

### M01 recall boundary

Headline equality alone does not collapse different URLs. Missing discovery-time
new-development metadata does not prove absence of a development. HOT, OLD, and
unknown publication observations set
`requires_m02_freshness_verification=true` and remain eligible for M02, subject to
normal scoring and shortlist limits. Only M02 may issue the terminal freshness
decision from exact-article evidence.
