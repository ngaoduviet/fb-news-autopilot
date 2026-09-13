# Production runbook

## Before each release

Run `.venv/bin/python -m pytest -q` and `git diff --check`. Confirm source scans contain
no model SDK/client, `.env` is ignored, `META_AUTO_PUBLISH=false` is the default, and
all Meta tests use injected transports. Review selector drift against live publishers.

## Shadow cycle

```sh
.venv/bin/fb-news-autopilot radar-run --run-id RUN_ID
.venv/bin/fb-news-autopilot validate-semantic --run-id RUN_ID
.venv/bin/fb-news-autopilot validate-editorial --run-id RUN_ID
.venv/bin/fb-news-autopilot run-cycle --run-id RUN_ID
```

Render with an explicit approved file, or omit the image arguments to use a configured
owned fallback from `config/image_sources.yaml`:

```sh
.venv/bin/fb-news-autopilot render --run-id RUN_ID --news-id NEWS_ID \
  --source-image /absolute/approved-source.png --image-rights PERMITTED
.venv/bin/fb-news-autopilot select-publishable --run-id RUN_ID
.venv/bin/fb-news-autopilot publish --run-id RUN_ID --news-id NEWS_ID --dry-run
```

Full automatic rendering works only when `config/image_sources.yaml` maps the relevant
topic (or `default`) to an approved local fallback file. Every fallback must have an
explicit `OWNED`, `LICENSED`, or `PERMITTED` rights state. An article
`source_image_url` with `UNKNOWN` rights is discovery metadata only and is never selected
or downloaded automatically. When `fallbacks: {}` and no explicit approved asset is
provided, the cycle must stop with `HOLD_IMAGE_RIGHTS`; it must not manufacture an image
or infer reuse rights from the publisher page.

## Holds and recovery

- Semantic/editorial HOLD: correct the current run artifact from exact evidence, then
  rerun validation. Never edit the candidate/evidence files.
- `HOLD_IMAGE_RIGHTS`: obtain documented permission or select an owned/licensed asset.
- Meta preflight failure: keep publishing disabled and resolve the classified Page,
  credential, or API error in Meta's tools. A successful runtime identity check does not
  verify provisioning tasks, user/app permissions, or actual publish/comment authority;
  those remain separate setup evidence and explicit-test blockers.
- `PUBLISHED_COMMENT_PENDING`: retry only the comment when a confirmed `post_id` exists.
  Never use `photo_id` as the comment target, delete the reservation, or recreate the post.
- A reservation with no `post_id` after an uncertain network result requires manual
  Graph API/Page reconciliation before any retry.

Back up `data/history/fb_news_autopilot.db` and queue artifacts. Rollback means disabling
the kill switch and deploying the previously reviewed code; never erase audit history.
