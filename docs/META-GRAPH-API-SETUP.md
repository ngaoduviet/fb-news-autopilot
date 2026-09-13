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

6. Run `.venv/bin/fb-news-autopilot meta-preflight`. With the Page Access Token it makes
   one read-only request for `GET /{META_PAGE_ID}?fields=id,name`, verifies the exact Page
   ID, requires a Page name, and reports whether runtime identity was verified. It does
   not request `tasks` from the Page object and does not call `/me/permissions`.
7. Capability tasks are provisioning evidence. Obtain them through Meta's documented
   `GET /me/accounts?fields=id,name,access_token,tasks` flow using a User Access Token
   outside production runtime. If the non-secret evidence is recorded in
   `config/meta.yaml`, include only `page_id`, `page_name`, `tasks`,
   `normalized_capabilities`, `verified_at`, and `graph_api_version`; never include
   either access token. The loader recomputes normalized capabilities and rejects the
   record if its declared values do not match the raw tasks. Legacy `CREATE_CONTENT` and
   `MODERATE`, New Page Experience `PROFILE_PLUS_CREATE_CONTENT` and
   `PROFILE_PLUS_MODERATE`, and `PROFILE_PLUS_FULL_CONTROL` are normalized into the
   stable `publish_content` and `moderate` capabilities. The current record contains the
   non-secret v26.0 result for Page `1215703644949288`, verified on 2026-09-13. If the
   record is removed, preflight reports `NOT_RUNTIME_VERIFIABLE` rather than inventing a
   result.
8. User/app permission grants remain a provisioning/setup concern. Runtime reports
   `NOT_DIRECTLY_VERIFIABLE_WITH_PAGE_TOKEN`; it does not treat Page-token
   `/me/permissions` as proof. Explicit publish and comment authorization must be proven
   later in an operator-controlled test before the publication gate can be enabled.
9. Validate response shape and Page visibility with an operator-controlled test process
   before considering `META_AUTO_PUBLISH=true`. The repository's default tests never
   make a Meta request and no live publish test is enabled.

## Preflight evidence boundary

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

The runtime now treats a successful Page-token response as Page identity evidence only.
A passing runtime preflight is not production publication authorization. Capability
status comes only from the optional non-secret provisioning record, while permissions
and actual publish/comment authorization remain explicitly unverified. The publication
command therefore remains held with `HOLD_META_PUBLISH_AUTHORIZATION_UNVERIFIED` even
after identity succeeds. Do not add a User Access Token to production runtime. Keep
`META_AUTO_PUBLISH=false` until a separate reviewed change records the explicit test
result and enables the publication authorization gate.

The application does not need or store an App Secret at runtime for these Page-token
operations. Keep any App Secret solely in Meta/secret-management setup where required.
