# PACKAGE 01 — MANIFEST

## Included Files

1. `AGENTS.md` — repository operating map and hard rules.
2. `ARCHITECTURE.md` — Package 01 component design and module boundaries.
3. `DATA-CONTRACT.md` — structured inter-module data model, statuses, rejection/review codes, score formulas.
4. `skills/news-radar/SKILL.md` — M01 News Radar, derived from Tin Nóng 5s Radar V3.0 rules.
5. `skills/source-verifier/SKILL.md` — M02 Source Verifier.
6. `config/publishers.yaml` — starter Vietnamese publisher/selector registry.
7. `src/fb_news_autopilot/discovery/` — deterministic RSS and hybrid adapters.
8. `src/fb_news_autopilot/queueing.py` — immutable evidence queue and Codex semantic handoff.
9. `src/fb_news_autopilot/history.py` — idempotent SQLite run and event history.
10. `src/fb_news_autopilot/shadow.py` — Package 01-only live shadow runner/report.
11. `LIVE-SHADOW-GUIDE.md` and `LIVE-SHADOW-REPORT.md` — operation and readiness evidence.

## Package Boundary

This package intentionally excludes:

- editorial/caption generation;
- first-comment generation;
- image-prompt generation;
- monetization compliance module;
- image generation;
- Facebook publishing;
- analytics/performance feedback.

Those remain outside M01/M02. Repository-level automation adapters prepare and guard
those later actions without changing Package 01 verification authority.

## Pending Confirmation Before Package 02

The operator has indicated that existing Editorial Generator instructions already exist. Those instructions should be imported as source material rather than recreated from scratch when M04 is built.

## Current Engineering Boundary

Package 01 supports manual offline execution and opt-in live shadow execution. It ends
after M02 verification, immutable audit persistence and SQLite history. Package 02 and
all publishing behavior remain excluded pending separate acceptance.
