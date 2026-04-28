# _archive/

Files moved here are **superseded, obsolete, or of uncertain relevance** — never deleted. See GOVERNANCE §6.

## Conventions

- Move via `git mv`, never copy + delete.
- Add an entry to `MIGRATION-LOG.md` for every move.
- Preserve original folder structure when meaningful (`_archive/tickets/`, `_archive/guides/`, etc.) — or flatten if not.
- If relevance is uncertain, include the verification gate in the MIGRATION-LOG note: "verify X before promoting back to a real ticket."

## Why archive instead of delete

- Audit trail. Future-you (or an auditor) asks "what happened to X?" — `_archive/` answers with the original content.
- Storage cost is near-zero. Cognitive cost of premature deletion is high.
- Git history would survive deletion, but `_archive/` is faster to audit than `git log --all`.

## What does NOT belong here

- Active tickets — they live in `tickets/`.
- Done tickets — `tickets/done/` is the archive for shipped work.
- Drafts that haven't been promoted — keep them in `tickets/backlog/` until you decide.
