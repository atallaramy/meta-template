# Migration Log

Permanent audit trail of file moves and archival decisions. Append-only — never edit past entries.

**Why this file exists:** GOVERNANCE §6 forbids `rm`. When a file is superseded, obsolete, or its relevance is uncertain, it gets `git mv`'d to `_archive/`. This log records the move + reason so future audits can trace what happened to any document that ever lived in this repo.

---

## Format

Each entry:

```
### YYYY-MM-DD — <short title>

- **From:** `<old-path>`
- **To:** `<new-path>` (or `_archive/<...>` if archived)
- **Reason:** one sentence on why
- **Successor (if any):** `<path-to-the-replacement>`
```

For epic-registry additions, use the section below.

---

## Epic additions

*(Each entry: justification per GOVERNANCE §10 — why doesn't this fit an existing epic, scope, excludes, synonym aliases blocked.)*

*(none yet)*

---

## File moves
