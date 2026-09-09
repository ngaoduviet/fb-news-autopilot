# FB NEWS AUTOPILOT — PACKAGE 01 ARCHITECTURE

## 1. Objective

Package 01 establishes the ingestion and verification foundation for an automated Facebook news workflow. It deliberately stops before editorial generation so that later modules only receive current, traceable, verified source material.

## 2. Component Diagram

```text
┌───────────────────────────────┐
│ Trigger                       │
│ Manual / Codex Automation    │
│ Runtime timezone + run time   │
└───────────────┬───────────────┘
                ↓
┌───────────────────────────────┐
│ M01 — NEWS RADAR              │
│ - Discover                    │
│ - Normalize                   │
│ - Cluster                     │
│ - Preliminary rank            │
│ - Shortlist                   │
└───────────────┬───────────────┘
                ↓
        CANDIDATE_NEWS_PACKAGE[]
                ↓
┌───────────────────────────────┐
│ M02 — SOURCE VERIFIER         │
│ - Resolve exact article URL   │
│ - Validate page type          │
│ - Validate source             │
│ - Validate publication time   │
│ - Validate event time         │
│ - Validate factual support    │
│ - Duplicate/freshness gate    │
└───────────────┬───────────────┘
                ↓
       VERIFIED_NEWS_PACKAGE[]
                ↓
┌───────────────────────────────┐
│ PACKAGE 01 OUTPUT             │
│ Persist + audit + handoff     │
└───────────────────────────────┘
```

## 3. Separation of Concerns

### Trigger

Responsible only for initiating a run and passing runtime context:

- `run_id`
- `run_at`
- `timezone`
- `live_window_hours`
- optional category/source configuration

The trigger must not contain the substantive News Radar rules.

### M01 News Radar

M01 optimizes **recall + ranking**. It should find potentially useful current stories but does not have authority to finalize source validity.

### M02 Source Verifier

M02 optimizes **precision + provenance**. It is an independent gate. A high M01 score cannot force an M02 pass.

## 4. Freshness Model

### 4.1 LIVE WINDOW

Default:

```text
0–2 hours before run_at
```

Candidates in this window are eligible for normal current-news consideration, subject to all other checks.

### 4.2 HOT WINDOW

Default:

```text
>2 hours and ≤24 hours before run_at
```

A HOT WINDOW story may pass only if at least one of the following is verified:

- a materially new development occurred today;
- an official decision/update was issued today;
- new verified figures or consequences were published today;
- the current article itself reports a new phase of an ongoing event.

The system must record the new development in `freshness_basis`.

### 4.3 ARCHIVAL / OLD

Older than the allowed HOT WINDOW, or old event recirculated without new development:

```text
REJECT_OLD_NEWS
```

Importance, virality, or social interest does not override this rule.

## 5. URL Validation Model

Discovered URLs are untrusted until M02 validates them.

### Allowed final source URL

A URL that resolves to the exact detailed news/article page supporting the candidate story.

### Invalid final source URL classes

- publisher homepage;
- section/category page;
- topic/tag page;
- search-results page;
- generic portal landing page;
- aggregator summary when an origin article is available;
- URL that only redirects to a non-article page;
- dead/inaccessible URL with no verifiable article content.

M02 stores both:

- `discovered_url`
- `resolved_article_url`

They may be identical, but must not be assumed identical.

## 6. Source/Origin Model

Each candidate may have multiple coverage URLs. The system should group them under one `story_cluster_id` when they refer to the same underlying event/development.

Preferred source selection principles:

1. Primary/official source when it contains the actual decision/data/event statement.
2. Direct reputable news article with sufficient factual detail.
3. Secondary reputable coverage for corroboration.

The source verifier should not substitute a low-quality aggregator for an available origin source.

Numeric source-reliability thresholds and publisher allow/deny lists are intentionally runtime-configurable and are not hardcoded in Package 01.

## 7. Duplicate Model

Duplicate detection should operate at two levels:

### A. URL duplicate

Same canonical/resolved URL.

### B. Semantic event duplicate

Different publishers or URLs covering materially the same event/development.

The system should select a representative source but preserve corroborating URLs where useful.

A later production system should also compare against previously published story fingerprints before Facebook publishing.

## 8. Scoring Architecture

Scoring occurs after basic normalization but before final selection.

### Hot Score

```text
0.25 viral_potential
+ 0.25 direct_life_impact
+ 0.20 money_benefit_value
+ 0.15 emotional_pull
+ 0.10 debate_potential
+ 0.05 freshness_score
```

All component scores are normalized to 0–100.

### Top Content Score

```text
0.40 hot_score
+ 0.30 audience_quality_score
+ 0.20 money_value_score
+ 0.10 production_score
```

Scores guide priority only. A candidate with `verification_status=REJECTED` is never selectable.

## 9. Tin Nóng 5s Topic-Priority Profile

Default V3 profile:

| Portfolio | Guideline | Examples |
|---|---:|---|
| Money & Policy | 30% | tax, land, benefits, wages, gold, interest rates, direct policy impact |
| Breaking / Social | 25% | major accidents, official breaking developments, important public events |
| Life Alert | 20% | safety, consumer warnings, weather/public-risk alerts, practical impact |
| Tech / Trend | 15% | major technology/platform/AI trends with broad interest |
| Global / Sport / Entertainment | 10% | major international, sport or entertainment developments |

These are selection preferences across a stream of runs, not mandatory quotas per individual run.

## 10. Failure Handling

### Source unavailable

Do not infer missing article facts. Set a deterministic failure/review code.

### Publication time unclear

If freshness cannot be established reliably:

```text
REVIEW_PUBLICATION_TIME_UNCLEAR
```

Do not classify it as breaking news.

### Event time unclear

If article freshness is valid but the underlying event date is ambiguous, M02 may return `REVIEW` rather than `VERIFIED` when the ambiguity materially affects the current-news claim.

### No valid candidates

Return `NO_VERIFIED_CANDIDATES`. Never relax freshness or URL rules to fill a quota.

## 11. Auditability

Every run should persist:

- run context;
- raw candidate identifiers;
- discovered and resolved URLs;
- timestamps and timezone;
- scoring components;
- verification decision;
- rejection/review codes;
- evidence summary sufficient to reproduce the decision.

## 12. Package 01 Boundary

The following are explicitly future scope:

- caption generation;
- first-comment generation;
- image prompt generation;
- Facebook monetization gate;
- reference-image rights processing;
- image generation;
- Facebook publishing;
- first comment posting;
- post verification;
- performance feedback.
