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
    "new_development_claimed": false
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

## 5. SOURCE_VERIFICATION — M02 Output Block

```json
{
  "verification": {
    "status": "VERIFIED",
    "verified_at": "2026-09-09T05:06:00+07:00",
    "publisher_name": "...",
    "resolved_article_url": "https://publisher.example/exact-article",
    "canonical_url": "https://publisher.example/exact-article",
    "page_type": "ARTICLE",
    "article_accessible": true,
    "publication_time": "2026-09-09T04:40:00+07:00",
    "publication_time_confidence": "HIGH",
    "event_time": "2026-09-09T03:55:00+07:00",
    "event_time_confidence": "MEDIUM",
    "freshness_bucket": "LIVE",
    "freshness_basis": "Article and event both fall within the live window.",
    "headline_supported": true,
    "facts_supported": true,
    "origin_quality": "DIRECT_REPUTABLE_ARTICLE",
    "corroborating_urls": [],
    "rejection_codes": [],
    "review_codes": []
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

A candidate in `REVIEW` must not be automatically passed to a future auto-publishing path.

## 8. VERIFIED_NEWS_PACKAGE — Package 01 Final Object

```json
{
  "schema_version": "1.0.0",
  "run_context": {},
  "news_id": "TN5S-20260909-001",
  "story_cluster_id": "cluster-...",
  "source": {
    "publisher_name": "...",
    "discovered_url": "https://...",
    "resolved_article_url": "https://...",
    "canonical_url": "https://...",
    "publication_time": "2026-09-09T04:40:00+07:00",
    "event_time": "2026-09-09T03:55:00+07:00",
    "corroborating_urls": []
  },
  "content": {
    "verified_title": "...",
    "verified_summary_facts": ["..."],
    "main_entities": ["..."],
    "topic": "money_policy",
    "location": "..."
  },
  "freshness": {
    "bucket": "LIVE",
    "age_hours": 0.4,
    "basis": "..."
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
    "headline_supported": true,
    "facts_supported": true,
    "origin_quality": "DIRECT_REPUTABLE_ARTICLE",
    "rejection_codes": [],
    "review_codes": []
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
