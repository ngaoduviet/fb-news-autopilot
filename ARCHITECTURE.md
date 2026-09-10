# FB NEWS AUTOPILOT — PACKAGE 01 ARCHITECTURE

## 1. Objective

Package 01 establishes the ingestion and verification foundation for an automated Facebook news workflow. It deliberately stops before editorial generation so that later modules only receive current, traceable, verified source material.

## 2. Component Diagram

```text
┌───────────────────────────────┐
│ Trigger                       │
│ Manual shadow run            │
│ Runtime timezone + run time   │
└───────────────┬───────────────┘
                ↓
┌───────────────────────────────┐
│ DETERMINISTIC DISCOVERY       │
│ Configured RSS/Atom feeds     │
│ Discovery evidence only       │
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
       VERIFIED / REVIEW / REJECTED[]
                ↓
┌───────────────────────────────┐
│ PACKAGE 01 OUTPUT             │
│ SQLite history + audit/report │
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
For observed HOT or OLD publication times, absence of a discovery-time development
hint is not evidence that no current development exists. M01 marks the candidate as
requiring M02 freshness verification and preserves it for the shortlist, subject to
the normal limit and scoring. M01 may deterministically collapse only identical
normalized URLs or identical explicit reliable event keys; headline equality alone
is only a hint and cannot cause rejection.

Configured RSS/Atom sources implement the discovery interface. Feed summaries remain
discovery provenance. Hybrid deduplication uses normalized URLs or explicit event keys;
equal headlines alone remain separate observations.

### M02 Source Verifier

M02 optimizes **precision + provenance**. It is an independent gate. A high M01 score cannot force an M02 pass.
It fetches the exact article with bounded HTTPS requests and applies publisher-specific
rules from `config/publishers.yaml`. Non-deterministic support decisions cross a file
boundary to Codex Automation. `semantic_decisions.json` and every quotation are validated
before the deterministic status gate. Missing, ambiguous, or ungrounded output is held;
it never defaults to VERIFIED.

## 4. Freshness Model

Retain original `publication_time`, nullable `last_updated_time`, and nullable
`material_development_time` separately. Compute `effective_freshness_time` from:

1. verified material development time supported by the exact source article;
2. verified substantive update time supported by that article;
3. original publication time.

With the default windows, LIVE means age 0–2 hours; HOT means age >2 and
≤24 hours; OLD means age >24 hours. HOT still requires a verified material
new development today, in the run's business timezone.

An article published more than 24 hours ago can qualify only if the exact article
contains and substantiates a new material development or substantive update
inside the permitted window. Evidence in another article cannot refresh this
article: discover and verify that other source separately. Cosmetic updates,
rewrites, republication, and social recirculation never reset freshness.
Record the selected timestamp and evidence in `freshness`.

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

Compare a normalized canonical/resolved URL together with the verified development
identity. The same URL and same non-null verified event key is a duplicate. The same
URL and a different non-null verified event key is a new phase, not a duplicate.
If the URL is reused but event identity is unresolved, return
`REVIEW_DUPLICATE_UNCERTAIN`.

### B. Semantic event duplicate

Different publishers or URLs covering materially the same event/development.
The same non-null verified event key is a duplicate across URLs.

The system should select a representative source but preserve corroborating URLs where useful.

A later production system should also compare against previously published story fingerprints before Facebook publishing.

Duplicate history records retain at least normalized URL, verified event key, and
effective freshness time. A single URL set is not sufficient duplicate evidence.

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

SQLite persists runs, candidates, terminal verifications and verified event history.
The immutable content-addressed JSON audit retains raw observations and fetched evidence.
Unexpected run/candidate errors create sanitized failure records. A candidate exception
does not prevent independent candidates from completing where isolation is safe.

`news_id` identifies a candidate inside one run: SHA-256 of contract version, `run_id`,
and an explicit event key or normalized URL. `story_cluster_id` is the cross-source M01
grouping hint. Cross-run duplicate identity comes from M02 `verified_event_key` and
persistent event history, never from `news_id`.

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

Repository-level automation adapters for strict editorial validation, local rendering,
and disabled-by-default Meta integration do not change this boundary: M01/M02 never
generate copy or publish. Codex Automation is the separate orchestration/editorial layer.
