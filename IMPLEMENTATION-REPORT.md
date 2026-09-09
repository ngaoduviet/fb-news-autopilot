# Package 01 — implementation report

Implemented M01 discovery/ranking and M02 independent verification, JSON schemas,
automated tests and append-only audit persistence. Package 01 stops at the verified
news package. No Package 02, scheduling, credentials, Meta API or publishing integration.

## Validation results

- `.venv/bin/python -m pytest -q -p no:cacheprovider`: **118 passed**, including every required A–M case,
  all 15 hard rejection codes and all 9 review codes.
- `.venv/bin/fb-news-autopilot --input examples/manual-run.json --output runs`:
  **NO_VERIFIED_CANDIDATES**, with persisted audit JSON (expected for an empty run).
- `.venv/bin/python -m compileall -q src`: passed.
- `git diff --check`: passed.
- Tests use fixture sources/model responses. No claim is made that a real publisher
  or live model integration was validated. No code was committed or pushed.

## Modified existing files

- `AGENTS.md`: normalize HOT wording and clarify M01 freshness/duplicate boundaries.
- `ARCHITECTURE.md`: effective freshness, direct-article, M01 recall, and event-aware duplicate rules.
- `DATA-CONTRACT.md`: unified terminal example, approved amendments, new review
  codes, schema mapping and raw-evidence preservation.
- `skills/news-radar/SKILL.md`: consistent HOT window, M02 freshness handoff, and safe clustering boundary.
- `skills/source-verifier/SKILL.md`: effective freshness, access mapping, semantic
  uncertainty, unified terminal output.

`PACKAGE-01-MANIFEST.md` and `.gitattributes` are unchanged. Existing Markdown files
were preserved and updated only within the approved clarification scope.

## Added files

- `.gitignore`, `.env.example`, `pyproject.toml`: environment, packaging and test setup.
- `schemas/*.schema.json` (7): validated candidate, context, verification, terminal,
  verified-only, radar-summary and run-result contracts.
- `scripts/build_schemas.py`: reproducible schema generation.
- `src/fb_news_autopilot/__init__.py`: public Package 01 classes.
- `models.py`, `contracts.py`: immutable typed evidence, IDs, runtime and schema validation.
- `radar.py`: observations, preliminary gates, clustering, weighted ranking and shortlist.
- `sources.py`: bounded HTTPS fetching, redirects, publisher identity, HTML and RSS/Atom.
- `semantic.py`: vendor-neutral structured model adapter with evidence quotation checks.
- `verifier.py`: independent deterministic source/freshness/support/duplicate gates.
- `pipeline.py`: outcomes and append-only evidence persistence.
- `cli.py`: explicit manual-run entry point.
- `tests/conftest.py`: reusable local fixtures.
- `tests/test_verifier.py`: all decision codes, freshness, duplicates, evidence retention.
- `tests/test_radar_contracts_pipeline.py`: ranking, schemas, runtime, audit and outcomes.
- `tests/test_sources.py`: HTML/RSS extraction, blocked pages, publisher configuration.
- `tests/test_semantic.py`: structured assessment, exact quote anchoring and safe fallback.
- `examples/manual-run.json`: empty offline configuration; no source credentials.
- `README.md`, `IMPLEMENTATION-REPORT.md`: usage, boundaries, limitations and delivery report.

## Interpretations and operational limits

The approved clarification controls freshness: verified exact-article material development,
then substantive update, then publication time. HOT still requires a material development
today because the approval did not remove that existing gate. Missing publication metadata
remains REVIEW under the explicit publication-time rule. HTTPS follows DATA-CONTRACT's
higher-priority URL convention; raw malformed URL strings are preserved only for ingress
rejection and audit, not as valid candidate or resolved source URLs.

Subjective ratings and source reputation are explicit input/configuration. Unavailable
scores are audited rather than invented. The optional model transport must be connected
to an approved provider by the operator. Without it, contextual claim support stays REVIEW;
the CLI does not silently call a model. The generic HTML parser supports common markup,
not every publisher. Cross-publisher event dedup requires independently verified event keys.

Acceptance Fix Round 1 corrected four defects: configured category paths now precede
article signals and generic `<article>` cards cannot prove a direct article; duplicate
history combines normalized URL, verified event key, and effective freshness time;
headline equality alone no longer collapses different M01 URLs; and HOT/OLD/unknown
observations without a development hint remain eligible for M02 with an explicit
freshness-verification flag.

These are documented implementation/configuration boundaries. No additional unresolved
business-rule contradiction was identified after applying the approved clarifications.

## Final source tree

Generated environments, caches, installation metadata and ignored run evidence are omitted.

```text
fb-news-autopilot/
├── examples/
│   └── manual-run.json
├── schemas/
│   ├── candidate-news-package.schema.json
│   ├── package-01-result.schema.json
│   ├── radar-summary.schema.json
│   ├── run-context.schema.json
│   ├── run-result.schema.json
│   ├── source-verification.schema.json
│   └── verified-news-package.schema.json
├── scripts/
│   └── build_schemas.py
├── skills/
│   ├── news-radar/
│   │   └── SKILL.md
│   └── source-verifier/
│       └── SKILL.md
├── src/
│   └── fb_news_autopilot/
│       ├── __init__.py
│       ├── cli.py
│       ├── contracts.py
│       ├── models.py
│       ├── pipeline.py
│       ├── radar.py
│       ├── semantic.py
│       ├── sources.py
│       └── verifier.py
├── tests/
│   ├── conftest.py
│   ├── test_radar_contracts_pipeline.py
│   ├── test_semantic.py
│   ├── test_sources.py
│   └── test_verifier.py
├── .env.example
├── .gitattributes
├── .gitignore
├── AGENTS.md
├── ARCHITECTURE.md
├── DATA-CONTRACT.md
├── IMPLEMENTATION-REPORT.md
├── PACKAGE-01-MANIFEST.md
├── README.md
└── pyproject.toml
```
