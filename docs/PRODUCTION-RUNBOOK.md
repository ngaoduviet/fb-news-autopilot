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

## Gate 6 one-shot Meta test

Gate 6 is a manual single-image authorization test. It is not an automation switch.
Keep `META_AUTO_PUBLISH=false`, do not start a scheduler, and use a fresh candidate that
appears in `select-publishable`. Confirm the rendered manifest says `OWNED`, `LICENSED`,
or `PERMITTED`; the poster must be one 1080x1350 image.

The operator must already have `META_PAGE_ID`, `META_PAGE_ACCESS_TOKEN`, and
`META_GRAPH_API_VERSION` in the local process environment. Run exactly one command,
replacing `RUN_ID` and `NEWS_ID` with the reviewed selection:

```sh
META_LIVE_PUBLISH_TEST=1 META_AUTO_PUBLISH=false \
  .venv/bin/fb-news-autopilot meta-live-publish-test \
  --run-id RUN_ID \
  --news-id NEWS_ID \
  --confirm-page-id 1215703644949288
```

The command fails before a Meta write unless the confirmation matches the runtime Page,
preflight identity succeeds, provisioning proves `publish_content` and `moderate`, the
candidate and editorial pass, deterministic selection includes the item, and the
single-image asset and idempotency gates pass. If `META_AUTO_PUBLISH=true`, it fails
closed even when the live-test switch is set.

Immediately before the first write, the command prints one JSON `PRE_WRITE_SUMMARY`
containing the run and news IDs, Page ID/name, source name/URL, absolute rendered image
path, rights status, `[1080,1350]` dimensions, `SINGLE` layout, caption and comment
character counts, five-hashtag confirmation, idempotency key, and `auto_publish:false`.
It never prints the token. The next output is the final result. Full success reports
`ok:true`, a state of `COMMENTED` or `VERIFIED_ON_FACEBOOK`, distinct `photo_id`,
`post_id`, and `comment_id` values when Meta returns them, and
`publication_authorization:EXPLICITLY_VERIFIED`.

Expected pre-write shape:

```json
{
  "event": "PRE_WRITE_SUMMARY",
  "mode": "PHOTO_AND_COMMENT",
  "run_id": "RUN_ID",
  "news_id": "NEWS_ID",
  "page_id": "1215703644949288",
  "page_name": "Tin Nóng 5s",
  "source_name": "SOURCE",
  "source_url": "https://source.example/direct-article",
  "rendered_image_path": "/absolute/path/poster.png",
  "image_rights_status": "OWNED",
  "image_dimensions": [1080, 1350],
  "image_layout": "SINGLE",
  "caption_character_count": 123,
  "exactly_5_hashtags_confirmed": true,
  "first_comment_character_count": 456,
  "idempotency_key": "sha256-value",
  "auto_publish": false
}
```

Expected success shape:

```json
{
  "ok": true,
  "state": "VERIFIED_ON_FACEBOOK",
  "run_id": "RUN_ID",
  "news_id": "NEWS_ID",
  "page_id": "1215703644949288",
  "idempotency_key": "sha256-value",
  "publication": {
    "photo_id": "META_PHOTO_ID",
    "post_id": "META_POST_ID",
    "status": "VERIFIED_ON_FACEBOOK"
  },
  "comment": {
    "post_id": "META_POST_ID",
    "comment_id": "META_COMMENT_ID"
  },
  "publication_authorization": "EXPLICITLY_VERIFIED",
  "authorization_evidence_path": "/absolute/path/meta-publication-authorization.json",
  "auto_publish": false
}
```

If Meta returns `photo_id` without `post_id`, the command records
`RECONCILIATION_REQUIRED`, does not comment, and never retries the photo. Inspect the
Tin Nóng 5s Page and the Graph response using Meta's operator tools. Match the creation
time, image, caption, Page ID, and stored photo ID. Preserve the database and stop until
a reviewed reconciliation procedure can record a confirmed post ID; do not guess or use
the photo ID as the comment target.

If a confirmed post exists but the first comment fails, the state is
`PUBLISHED_COMMENT_PENDING`. Correct the external problem, then rerun the same exact
Gate 6 command with the same run, news ID, Page confirmation, history database, and
environment guards. The idempotency record switches the operation to
`COMMENT_ONLY_RETRY`; the photo endpoint is not called again.

After both writes succeed, the command creates
`data/config/meta-publication-authorization.json`. It contains only Page ID, Graph API
version, test timestamp, the `photo_publish` and `first_comment` operation names, their
`EXPLICITLY_PROVEN` statuses, and a success flag. It contains no token. Subsequent Meta
preflight reports `publication_authorization:EXPLICITLY_VERIFIED`; this does not change
`META_AUTO_PUBLISH` or start a scheduler. The dedicated command then returns
`HOLD_GATE6_ALREADY_COMPLETED` before any later photo write, even for another story.

If the operator removes the test post, first save the non-secret post/comment IDs and
current state. Delete the confirmed `post_id` through the Tin Nóng 5s Page UI or an
operator-controlled Meta tool, verify that it no longer appears, and retain all local
publication history and authorization evidence as an audit of the completed test. Never
delete SQLite rows, reuse the old idempotency key, or issue a second photo post as a
rollback action.
