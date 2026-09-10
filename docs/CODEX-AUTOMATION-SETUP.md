# Codex Automation setup

Create a recurring Codex Desktop Automation for this repository at 05:00, 11:00, and
20:00 using timezone `Asia/Ho_Chi_Minh`. Its prompt should instruct Codex to follow
`AUTOMATION.md` exactly, use the repository-level verifier/editorial skills, remain quiet
when a cycle only produces ordinary holds/no candidates, and notify on completion,
failure, or required operator action.

Keep the working directory fixed to the repository. Install dependencies once with:

```sh
.venv/bin/python -m pip install -e '.[test]'
```

The task must generate a unique run ID, write only within that run directory, and never
edit prior immutable evidence. It must stop on validation failures. Semantic/editorial
reasoning happens in the Codex task itself through file reads/writes; no Python model
client, unofficial bridge, or paid model endpoint is allowed.

Start in shadow mode. Leave `META_AUTO_PUBLISH=false` until the Meta app, Page identity,
permissions, live response shapes, image-rights procedure, and operational review have
all been validated separately.
