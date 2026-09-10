# Meta Graph API setup

The adapter uses official Graph API endpoints only. As checked on 2026-09-10, Meta's
Page Photos reference documents `POST /{page-id}/photos` and accepts a local multipart
`source`; the comments edge is used for `POST /{post-id}/comments`. Because versions,
review requirements, response fields, and Page task behavior change, set the API version
explicitly and confirm the current references before enabling production:

- [Page Photos reference](https://developers.facebook.com/docs/graph-api/reference/page/photos/)
- [Object Comments reference](https://developers.facebook.com/docs/graph-api/reference/object/comments/)
- [Pages API getting started](https://developers.facebook.com/docs/pages-api/getting-started/)
- [pages_manage_posts](https://developers.facebook.com/docs/permissions/reference/pages_manage_posts)
- [pages_manage_engagement](https://developers.facebook.com/docs/permissions/reference/pages_manage_engagement)

## Operator setup

1. In Meta for Developers, create/select the app owned by the appropriate Business and
   add the Facebook Pages product/use case supported by the current dashboard.
2. Add the operator as a tester/developer during development and connect the intended
   Tin Nóng 5s Page through Meta Business settings.
3. Request only the permissions confirmed by the current dashboard and review flow.
   Publishing commonly involves `pages_show_list`, `pages_read_engagement`, and
   `pages_manage_posts`; Page comments commonly involve `pages_manage_engagement`.
   Treat Meta's current App Review and API response as authoritative.
4. Obtain the Page access token through Meta's supported flow. Store it in the process
   environment or an OS secret manager, never in Git, Markdown, shell history, or reports.
5. Set locally:

```sh
export META_PAGE_ID='your-page-id'
export META_PAGE_ACCESS_TOKEN='value-from-meta-secret-storage'
export META_GRAPH_API_VERSION='current-supported-version'
export META_AUTO_PUBLISH=false
```

6. Run `.venv/bin/fb-news-autopilot meta-preflight`. It checks configuration, retrieves
   `id,name,tasks` plus the token permission response, verifies the expected Page ID,
   and compares both responses with `config/meta.yaml`. Legacy `CREATE_CONTENT` and
   `MODERATE` tasks and New Page Experience `PROFILE_PLUS_CREATE_CONTENT`,
   `PROFILE_PLUS_MODERATE`, and `PROFILE_PLUS_FULL_CONTROL` are normalized into the
   stable `publish_content` and `moderate` capabilities. Permissions remain a separate
   gate. The result reports raw tasks, normalized capabilities, granted permissions,
   missing capabilities, and missing permissions; it does not print the token.
7. Validate response shape and Page visibility with an operator-controlled test process
   before considering `META_AUTO_PUBLISH=true`. The repository's default tests never
   make a Meta request and no live publish test is enabled.

## Preflight integration blocker

Meta's current official Postman collection documents Page task discovery through
`GET /me/accounts?fields=name,access_token,tasks` using a User Access Token. Its separate
request for one known Page also uses a User Access Token and requests `name,access_token`;
it does not demonstrate that `GET /{PAGE_ID}?fields=id,name,tasks` using the resulting
Page Access Token reliably returns `tasks`.

The documented permissions edge is `/{user-id}/permissions` and reports permissions
granted or declined by a User. The reviewed official material does not establish that
`GET /me/permissions` with a Page Access Token is complete app-permission evidence for
`pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, and
`pages_manage_engagement`.

The current implementation therefore remains a fail-closed read-only probe whose task
and permission response assumptions are unresolved until tested against the real Page,
app, API version, and Page token. Do not interpret a mocked preflight pass as production
authorization. Do not add a User Access Token to the production runtime during this
checkpoint. Keep `META_AUTO_PUBLISH=false`; after Meta is configured, capture only
sanitized response shapes and decide the final verification flow from that evidence.

The application does not need or store an App Secret at runtime for these Page-token
operations. Keep any App Secret solely in Meta/secret-management setup where required.
