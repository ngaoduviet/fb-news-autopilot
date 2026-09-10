# Package 01 live shadow readiness report

The Round 2 live probe established that configured RSS discovery, direct article
retrieval, publisher classification, and Vietnamese publication-time extraction work
against public sources. Publisher layouts and anti-bot behavior can drift, so the
opt-in RSS probe remains part of operational validation.

The architecture has since migrated to a file-driven Codex handoff. Model API probes
and credentials are obsolete. Semantic quality must be reviewed through saved exact
article evidence plus `semantic_decisions.json`; the default Python suite validates the
contract and quote grounding offline.

Run the current live fetch probe explicitly:

```sh
LIVE_TESTS=1 .venv/bin/python -m pytest -m live -q
```

This command does not call Meta and does not publish. Meta preflight is a separate,
read-only operator step documented in `docs/META-GRAPH-API-SETUP.md`.
