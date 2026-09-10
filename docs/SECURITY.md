# Security

Secrets belong in process environment variables or an OS/managed secret store. `.env`
and SQLite/runtime output are ignored. Never commit, paste into Codex prompts, print,
serialize, or log `META_PAGE_ACCESS_TOKEN`, authorization headers, app secrets, or full
environment dumps.

The shared redactor removes configured token values and common bearer/access-token/key
patterns before exceptions enter audit records. Meta audit entries contain only logical
endpoint name, HTTP status, duration, attempt, category, and timestamp. Tokens are sent
inside the HTTPS request body and are absent from endpoint URLs and audit JSON.

Article HTML and Codex-produced JSON are untrusted inputs. Paths are derived only from
safe run/news identifiers, JSON is schema validated, exact quotes are checked against
immutable article files, and semantic output cannot override URL/access/time gates.

If exposure is suspected, disable automation, leave auto-publish false, revoke/rotate
the token in Meta, inspect Git history and audit outputs without echoing the secret, and
record the incident separately from repository artifacts.
