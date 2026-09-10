# No-OpenAI-API Migration — Architecture Assessment

## Baseline audited

- Baseline command: `.venv/bin/python -m pytest -q`.
- Result before migration: 138 passed, 0 failed, 2 skipped.
- Working tree already contains accepted Package 01 Round 2 changes; they must be
  preserved. The migration is incremental and must not reset or clean the tree.
- Package 01 deterministic freshness, direct-article, duplicate, REVIEW/REJECTED,
  provenance and immutable-audit rules remain authoritative.

## Current architecture

The current shadow runner combines RSS with an OpenAI Responses API Web Search adapter,
then invokes an OpenAI Structured Outputs semantic transport during M02. Python performs
the remaining URL, source, freshness, duplicate, schema, audit and SQLite work. This
requires the OpenAI SDK plus three OpenAI environment variables and therefore conflicts
with the new runtime boundary.

## Target architecture

```text
Codex Automation schedule (05:00 / 11:00 / 20:00 Asia/Ho_Chi_Minh)
  -> Python deterministic RSS discovery, exact fetch and M01 queue
  -> data/queue/<RUN_ID>/candidates.json + immutable article evidence
  -> Codex semantic verification
  -> data/queue/<RUN_ID>/semantic_decisions.json
  -> Python strict fail-closed validation and Package 01 status persistence
  -> Codex editorial skill for VERIFIED + handoff_allowed only
  -> strict editorial JSON
  -> deterministic local 1080x1350 renderer + rights/compliance gates
  -> policy gate
  -> official Meta Graph API adapter when explicitly enabled
  -> idempotent first comment, verification, state/audit history
```

Python never invokes Codex or an OpenAI model. Codex Desktop Automation owns semantic
and editorial reasoning through files. A missing or invalid Codex output becomes HOLD;
it never defaults to VERIFIED.

## File impact matrix

| Action | Files/components | Reason |
|---|---|---|
| KEEP | `radar.py`, deterministic parts of `verifier.py`, `sources.py`, publisher registry, Package 01 terminal schemas/tests | Preserve accepted M01/M02 gates |
| MODIFY | `cli.py`, `shadow.py`, `history.py`, `models.py`, `pipeline.py`, schema builder, configuration, README/guides/specifications | Add queue/handoff/state boundaries and remove API configuration |
| DEPRECATE | OpenAI discovery and semantic transport interfaces during replacement phase | Keep tests green until queue validation is ready |
| DELETE | `discovery/openai_web.py`, `llm/openai_semantic.py`, obsolete OpenAI tests after replacement coverage passes | Remove production OpenAI calls and dependency |
| ADD | queue and handoff contracts, editorial contract/skill, image renderer, compliance/policy, Meta client/publisher/comment/preflight, state machine, automation docs/tests | Implement the target file-driven workflow |

## Migration phases

1. Remove OpenAI configuration from the application contract after strict queue and
   semantic-decision schemas exist.
2. Make RSS/configured feeds the deterministic radar input and write exact article
   evidence plus `candidates.json`.
3. Validate Codex-authored `semantic_decisions.json` fail-closed and map only validated
   decisions into Package 01 history.
4. Add the Tin Nóng 5s Codex editorial skill and strict editorial schema/validator.
5. Add local deterministic poster rendering and image-rights hold behavior.
6. Add mock-tested official Meta Graph API abstractions, safe preflight and idempotent
   comments without performing a real publish.
7. Add persisted publication state transitions, policy gates and retry idempotency.
8. Document Codex Automation and run-cycle orchestration; run full regression/security
   scans and remove obsolete OpenAI files/dependency.

Each phase must pass its relevant tests before the next phase changes runtime behavior.

## Risks and controls

- **Semantic output omission or corruption:** strict JSON Schema, run/news identity
  matching and HOLD on any missing/invalid file.
- **Quality regression after removing API calls:** Python does not replace semantics with
  keyword heuristics; Codex decisions require grounded quotes and existing hard gates.
- **Publisher HTML drift:** configuration-driven selectors, preserved raw evidence and
  REVIEW/REJECT on insufficient extraction.
- **Image copyright:** UNKNOWN rights produces `HOLD_IMAGE_RIGHTS` and cannot publish.
- **Duplicate Facebook posts after retry/crash:** state machine, publication history and
  canonical-URL/editorial-version idempotency key.
- **Secret exposure:** shared redaction, no token in URL/log/report, mocked default tests.
- **Meta permission/API drift:** environment-configured version, defensive response
  parsing, official documentation review and preflight classification.

## Rollback strategy

Migration changes remain uncommitted until acceptance. Each phase adds a file boundary
before removing its predecessor. If a phase fails, stop at the last passing file contract,
retain queued evidence and SQLite history, disable publishing with
`META_AUTO_PUBLISH=false`, and restore only the affected files from a reviewed patch.
Never reset or clean the whole working tree. OpenAI adapters may be removed only after
the RSS queue and semantic handoff tests pass.

## Acceptance criteria

- Full pytest has zero failures and no default external calls.
- Production source contains no OpenAI SDK import, client construction or API call and
  does not require OpenAI environment variables.
- Deterministic `radar-run` writes a schema-valid candidate queue with exact evidence.
- Semantic and editorial files validate strictly; missing/invalid files HOLD.
- REVIEW and REJECTED cannot reach editorial/publishing.
- Poster output is exactly 1080x1350, respects safe areas and requires allowed rights.
- Meta preflight/publish/comment behavior is mock-tested, redacted and off by default.
- State transitions and publication idempotency persist in SQLite.
- Codex Automation workflow, Meta setup, production operations and security are
  documented without secrets.

## Implemented status

The replacement path is active. RSS/configured discovery writes strict candidate queues
and immutable exact evidence. Codex semantic and editorial artifacts validate fail-closed.
The former model discovery/transport modules and dependency have been deleted.
Deterministic poster, rights, policy, Meta mock/preflight, comment idempotency,
publication state, automation configuration, and security documentation are present.
Real Meta publishing was not executed during migration and remains disabled by default.
