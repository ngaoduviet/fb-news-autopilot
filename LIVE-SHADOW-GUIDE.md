# API-free live shadow guide

The shadow path collects current configured RSS feeds, ranks observations with M01,
fetches exact articles, and writes a candidate queue. It never promotes a candidate to
`VERIFIED`; Codex Automation supplies the semantic decision file.

```sh
export FBNA_HISTORY_DB='data/history/fb_news_autopilot.db'
export FBNA_PUBLISHER_CONFIG='config/publishers.yaml'
.venv/bin/fb-news-autopilot shadow-run --queue-root data/queue
```

Each `data/queue/<run-id>/` contains `candidates.json`, `articles/`, `evidence/`, and
radar reports. Then follow [AUTOMATION.md](AUTOMATION.md). Missing or invalid semantic
and editorial artifacts stop dependent stages with a machine-readable HOLD code.

The offline suite performs no external calls. The RSS probe is separately enabled:

```sh
.venv/bin/python -m pytest -q
LIVE_TESTS=1 .venv/bin/python -m pytest -m live -q
```

Inspect all REVIEW/REJECTED reasons, exact quotes, source timestamps, and image rights.
Keep `META_AUTO_PUBLISH=false` throughout shadow validation.
