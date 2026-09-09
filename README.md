# FB NEWS AUTOPILOT — Package 01

Python implementation of M01 News Radar and M02 Source Verifier. Every run stops at
a traceable Package 01 result; there is no editorial generation or publishing code.
The approved clarifications are incorporated in the existing Markdown specifications.

## Install and test

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

Python 3.11+ is required. All tests are deterministic and use local fixture evidence;
no tests call a live news site or model service. No credentials are required.

## Manual use

```sh
.venv/bin/fb-news-autopilot --input examples/manual-run.json --output runs
```

The example is an empty, offline run illustrating the configuration shape. Set an
explicit current `run_at` with timezone offset for a real run. Configure publisher
hosts and observations or RSS/Atom feed URLs before attempting discovery. The CLI
prints the run outcome and an absolute path to the complete audit bundle.

Publisher configuration is a mapping from exact hostname to `name`, `origin_quality`,
optional `aliases`, `timezone`, `category_paths`, `article_selector`,
`article_path_patterns`, and `body_selector`. HTTP fetching
is restricted to configured HTTPS hosts, including every redirect destination. Source
quality is configured by the operator, not inferred from a publisher name or domain.
A missing/unclear identity cannot pass. Source timezones are used only when explicitly
configured; the business timezone is not substituted for a source timezone.

An observation has `url`, `headline`, `query_or_feed`, `discovered_at`, optional
`publisher`, `publication_time`, `topic`, `facts`, `entities`, `location`,
`new_development_claimed`, `event_key`, and `score_components`. Provide all nine
input score components from the data contract. `hot_score` and `top_content_score`
are calculated in Python. Subjective component ratings must come from an operator
or scoring adapter, not arbitrary fallback numbers. RSS accepts a scorer callable;
the CLI reads explicit ratings from `ratings_by_url`. Missing ratings are logged with
raw discovery evidence and are not fabricated to fill a shortlist.

## Module boundaries

- `radar.py`: observes publication times, marks non-LIVE observations for M02,
  clusters only identical normalized URLs or explicit event/development keys,
  computes configurable weighted scores, and shortlists. Headline equality alone
  never rejects different URLs. Ties use direct life impact, then portfolio
  preference, then stable ID. Portfolio percentages never force quotas.
- `sources.py`: independently fetches HTTPS articles, extracts HTML/JSON-LD evidence,
  follows allowed redirects, parses RSS/Atom, and records raw HTML. A discovery
  snippet cannot substitute for article content.
- `semantic.py`: optional structured model-assessment adapter for contextual headline
  support, factual support, material developments and semantic event identity.
- `verifier.py`: owns resolved article URLs, deterministic freshness and status gates,
  tri-state support, duplicate acceptance and handoff eligibility.
- `pipeline.py`: runs the two modules, validates outputs, and persists immutable audit
  bundles containing raw observations, full fetched HTML, extracted evidence and results.

## Semantic integration and limits

The repository does not select a model vendor or install credentials. To use an
approved model, supply a callable `complete(system_instruction, json_payload)` that
returns a dictionary conforming to the supplied response schema:

```python
assessor = StructuredSemanticAssessor(complete)
provider = WebSourceProvider(fetcher, publishers, semantic_assessor=assessor)
verifier = SourceVerifier(provider)
```

Import these classes from `fb_news_autopilot.semantic`, `.sources`, and `.verifier`.
Only semantic fields can be supplied by the assessor. It cannot overwrite fetched
body text, original publication/update metadata, URL, page type, publisher or final
status. True/false headline/fact decisions require exact supporting article quotes;
unanchored or malformed assessments remain unclear. Quote checks establish evidence
provenance, not model infallibility. The complete assessment explanation is audited.

Without a semantic assessor the CLI conservatively returns REVIEW for substantive
headline/fact claims: exact text matching alone cannot establish entailment. An explicit
adapter is needed for contextual decisions; there is no hidden model call. The default
adapter also cannot independently corroborate a blocked article, so it rejects such
sources. An independently corroborating provider may return the specified access REVIEW.

The generic HTML extractor handles common article/JSON-LD markup; publisher-specific
selectors and independent semantic assessment are necessary for unusual sites.
Configured category paths and homepage/search/tag/topic/aggregator signals take
precedence over article detection. A generic `<article>` element alone is not direct
article proof; structured article data, `og:type=article`, or an explicit publisher
article rule is required. Unrecognized page types cannot be verified. A timestamp alone never proves an update
is substantive. Confirmed updates/developments must be supported in the exact article.

## Determinism and evidence

- IDs are stable SHA-256 prefixes of normalized source URLs; clusters hash normalized
  URLs or explicit event/development keys. M01 cluster hints are not M02 proof.
- URL duplicate checks remove only recognized tracking parameters and fragments while
  retaining identifying query parameters. Duplicate history stores normalized URL,
  verified event key, and effective freshness time. The same event key rejects across
  URLs; a reused URL with a different non-null event key is a new phase; unresolved
  identity on a reused URL produces REVIEW. Supply a `DuplicateIndex` to retain
  previously accepted identities. Broader-topic matches alone do not reject new developments.
- The run's `run_at` is the reference for all freshness calculations. Verification time
  uses the actual clock; tests can inject a clock into `SourceVerifier`.
- HOT remains conditional on a material development today in the run's timezone.
  M01 never treats a missing development hint as proof of absence; HOT, OLD, and
  unknown observations are marked for M02 and remain shortlist-eligible.
  Original publication metadata is still required to be established (missing means
  REVIEW) even when a material development determines effective freshness.
- Rejections take precedence over reviews. All non-VERIFIED results have no verified
  text and cannot hand off. The full original candidate and raw source remain in audit.
- Identical audit bundles reuse their content-addressed path; different evidence creates
  a separate file and never overwrites an earlier bundle. Persisted data is under ignored
  `runs/`. This package has no global database or publisher history service.

## Validation and schema generation

Seven self-contained JSON Schema Draft 2020-12 files are checked in. Regenerate with
`python3 scripts/build_schemas.py`. Each candidate, verification block, terminal result,
radar summary and run result is validated at its module boundary. Timestamp offsets,
window ordering and dynamic evidence rules are additionally checked in Python.

The contract's HTTPS convention takes priority over the older HTTP(S) wording in M02.
Raw invalid URLs remain strings only at the ingress-error/audit boundary so their exact
input can be recorded as `REJECT_INVALID_URL`. No substitute source URL is emitted.
The canonical duplicate code is `REJECT_DUPLICATE_STORY`.

The tests cover all 15 rejection codes, all 9 review codes, required A–M cases, freshness
boundaries, old articles with genuine versus cosmetic updates, timezone handling,
source parsing, configured-category listing cards, schema bypass attempts, semantic
adapter failures, reused-URL event phases, headline-safe M01 clustering,
HOT-without-hint handoff, duplicate behavior,
run outcomes, and append-only persistence. See `IMPLEMENTATION-REPORT.md` for delivery
status and the complete source tree.
