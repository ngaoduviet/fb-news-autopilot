# PACKAGE 01 — MANIFEST

## Included Files

1. `AGENTS.md` — repository operating map and hard rules.
2. `ARCHITECTURE.md` — Package 01 component design and module boundaries.
3. `DATA-CONTRACT.md` — structured inter-module data model, statuses, rejection/review codes, score formulas.
4. `skills/news-radar/SKILL.md` — M01 News Radar, derived from Tin Nóng 5s Radar V3.0 rules.
5. `skills/source-verifier/SKILL.md` — M02 Source Verifier.

## Package Boundary

This package intentionally excludes:

- editorial/caption generation;
- first-comment generation;
- image-prompt generation;
- monetization compliance module;
- image generation;
- Facebook publishing;
- analytics/performance feedback.

Those belong to later packages/modules.

## Pending Confirmation Before Package 02

The operator has indicated that existing Editorial Generator instructions already exist. Those instructions should be imported as source material rather than recreated from scratch when M04 is built.

## Recommended Next Engineering Step

Use Codex to implement JSON schemas + automated tests for M01/M02 before building M04.
