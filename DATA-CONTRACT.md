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

`news_id` is a run-scoped candidate identity. Package 01 constructs it deterministically
as SHA-256 over `candidate-v2`, `run_id`, and a stable candidate key. The stable key is
an explicit reliable event key when present, otherwise the normalized discovered URL.
The same input in the same run has the same ID; the same URL in another run has a
different ID. `story_cluster_id` groups matching URL/event observations across sources
and is not a terminal duplicate decision.

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
    "publication_time_observed": "2026-09-09T04:40:00+07:00",
    "discovery_provider": "rss",
    "search_evidence": "Short factual discovery evidence only.",
    "citation_metadata": [
      {
        "reference_id": "source-1",
        "url": "https://publisher.example/article",
        "title": "...",
        "kind": "url"
      }
    ]
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

`discovery_provider` records `manual`, `rss`, a configured feed adapter, or a deterministic merged
provider label. Discovery evidence never establishes article accessibility,
freshness, semantic support, `resolved_article_url`, or terminal status.

### Fetched article evidence

The immutable source-evidence audit records `requested_url`, `final_url`,
`canonical_url`, `http_status`, `redirect_outcome`, `content_type`, `fetched_at`,
`publisher_host`, extracted title/body, source publication/update times, and raw
document where available. These fields describe the exact request; only M02 can map
them to terminal source fields.

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

The example below illustrates VERIFIED. All terminal statuses use these same top-level fields in this section. VERIFIED_NEWS_PACKAGE is the VERIFIED-only subset.

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
- `candidate-queue.schema.json`: deterministic RSS candidates plus exact evidence paths.
- `semantic-decisions.schema.json`: strict Codex semantic handoff and status/handoff rules.
- `editorial.schema.json`: strict Tin Nóng 5s editorial artifact.
- `rendered-asset.schema.json`: immutable poster hash, dimensions, and confirmed rights.

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

## 14. Round 2 persistent history and failure contract

SQLite persists `runs`, `candidates`, `verifications`, and `event_history`. Candidate
and verification records are idempotent by `news_id`. Event history retains normalized
URL, nullable verified event key, effective freshness time, and first/last run IDs.
The same event key is duplicate across URLs; a reused URL with a different non-null
verified event key is a new phase; uncertain identity on a reused URL is REVIEW.

Unexpected failures are stored in `run_failures` with only `run_id`, stage, exception
type, sanitized message and timestamp. Keys, authorization headers and environment
dumps are forbidden. One candidate failure may produce `RUN_PARTIAL_FAILURE` while
independent candidates complete.

Semantic-provider uncertainty does not by itself imply development uncertainty. For an
article whose verified publication time already places it in LIVE, a generic semantic
failure produces the applicable headline/fact support review codes without
`REVIEW_NEW_DEVELOPMENT_UNCLEAR`. That development review code applies when HOT/OLD
qualification depends on an unestablished material development/substantive update, or
when an explicit development/update claim exists but its support cannot be established.

## 15. Candidate queue and Codex semantic handoff

`candidate-queue.schema.json` defines `data/queue/<run_id>/candidates.json`. Every
shortlisted entry retains its complete M01 candidate contract, source/canonical URL,
exact article/evidence paths, extracted timestamps, deterministic checks, source image
URL, and `image_rights_status`. The default rights value is `UNKNOWN`; retrieval never
proves reuse rights. `needs_semantic_verification` is always true.

`semantic-decisions.schema.json` defines the only Codex-to-Python M02 semantic handoff.
It permits `VERIFIED`, `REVIEW`, and `REJECTED`, uses the rejection/review enums above,
and requires explicit tri-state support fields, exact evidence quotes, confidence, and
`handoff_allowed`. VERIFIED requires supported title/publication/facts, no unsupported
claims or reasons, and `handoff_allowed=true`. REVIEW and REJECTED require their own
reason family and `handoff_allowed=false`.

Python accepts the file only when the run ID and candidate coverage are exact, the
schema validates, VERIFIED does not override deterministic URL/article/time gates, every
quote occurs in the immutable article text, and every evidence URL matches the candidate.
Any failure produces a HOLD and no downstream eligibility.

## 16. Editorial handoff

`editorial.schema.json` defines `editorial/<news_id>.json`. It is valid only for a
VERIFIED semantic decision with `handoff_allowed=true`. It contains two captions, the
selected verbatim recommendation, exactly five unique hashtags, first comment and source
provenance, a 7–15-word headline split into 3–4 exact lines, at most two yellow keywords,
an audit-only image prompt, version/timestamp, and affirmative compliance fields.

Python additionally enforces caption 25–65 words, first comment 80–150 words, source and
news identity, line reconstruction, recommendation equality, and keyword containment.
It validates structure and eligibility; it does not generate or semantically improve copy.

## 17. Image and publication holds

`image_rights_status` is one of `OWNED`, `LICENSED`, `PERMITTED`, or `UNKNOWN`. Only the
first three may enter the deterministic renderer. UNKNOWN yields `HOLD_IMAGE_RIGHTS`.
The poster contract is 1080×1350 PNG/JPEG with validated safe margins.

Meta publishing is governed by `config/publish_policy.yaml` and the environment kill
switch. REVIEW, REJECTED, failed editorial compliance, unknown image rights, invalid
poster, duplicate publication, insufficient confidence, or failed preflight cannot
publish. The idempotency key is SHA-256 of canonical source URL plus editorial version.

## 18. Publication audit state

SQLite `state_transitions` records `run_id`, `news_id`, timestamp, previous/next state,
reason, and retry count. `publication_history` records the idempotency reservation and
normalized Page/photo/post identifiers. `comment_history` permits one recorded first
comment per post. A comment retry reuses the existing post and never creates another.
