# FB NEWS AUTOPILOT

Package 01 preserves M01 News Radar and M02 Source Verifier as the hard discovery and
verification boundary. The repository also contains file contracts and deterministic
adapters used by Codex Desktop Automation for editorial validation, poster rendering,
and a disabled-by-default Meta publishing path.

**FB News Autopilot does not require or use the OpenAI API. Semantic verification and
editorial generation are performed by Codex Automation outside the Python runtime.**

## Install and test

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

The default suite uses fixtures and mocked HTTP. The only news-site probe is opt-in:

```sh
LIVE_TESTS=1 .venv/bin/python -m pytest -m live -q
```

## File-driven workflow

```text
RSS/configured feeds -> M01 -> candidates.json + exact evidence
Codex semantic verifier -> semantic_decisions.json -> strict Python validation
Codex Tin Nóng 5s editor -> editorial/<news_id>.json -> strict Python validation
local Pillow renderer -> compliance/policy gate -> Meta adapter (off by default)
```

Start deterministic discovery:

```sh
.venv/bin/fb-news-autopilot radar-run --run-id TN5S-YYYYMMDD-HHMM
```

Validate Codex artifacts and inspect one cycle:

```sh
.venv/bin/fb-news-autopilot validate-semantic --run-id TN5S-YYYYMMDD-HHMM
.venv/bin/fb-news-autopilot validate-editorial --run-id TN5S-YYYYMMDD-HHMM
.venv/bin/fb-news-autopilot run-cycle --run-id TN5S-YYYYMMDD-HHMM
```

Candidate evidence is immutable under `data/queue/<run-id>/`. Missing, malformed,
uncovered, or ungrounded semantic output fails closed. `REVIEW` and `REJECTED` never
enter editorial or publishing. An image with `UNKNOWN` rights produces
`HOLD_IMAGE_RIGHTS`.

## Meta safety

`.env.example` contains empty placeholders. Keep real values outside Git.
`META_AUTO_PUBLISH` defaults to `false`; no default command or test publishes a post.

```sh
.venv/bin/fb-news-autopilot meta-preflight
.venv/bin/fb-news-autopilot publish --run-id RUN --news-id NEWS --dry-run
```

See [AUTOMATION.md](AUTOMATION.md), [the live shadow guide](LIVE-SHADOW-GUIDE.md), and
[the data contract](DATA-CONTRACT.md).
