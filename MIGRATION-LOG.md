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

### 2026-05-11 — Split flat best-practices.md into topic folder + wire agent Step 0

- **From:** `guidelines/best-practices.md`
- **To:** `guidelines/best-practices/overview.md` (folder)
- **Reason:** Flat-file format doesn't scale once a project accumulates project-specific learnings beyond the generic baseline. New folder layout: `core-loop.md` (rule #0 — write → review → community-check → loop), `overview.md` (cross-stack baseline — content unchanged, moved via `git mv`), plus topic files projects add as they learn (`cutover-patterns.md`, `dns-and-email.md`, `<framework>-patterns.md`, etc.).
- **Companion changes (same migration):**
  - `claude-config/agents/best-practices.md` — added Step 0 to Research Process: read `meta/guidelines/best-practices/*.md` first, `core-loop.md` first within that. Principles section reordered to put folder first.
  - `claude-config/CLAUDE.md` — "Pre-commit review gate" line replaced with "The Core Loop is rule #0" pointing at the new file; Guidelines section repointed at the folder.
- **Scope of the port:** universal pieces only — `core-loop.md`, `README.md` (with format spec + suggested topic-file names), `overview.md` move, agent Step 0 wire, CLAUDE.md rule. Any topic files (e.g. `cutover-patterns.md`, `dns-and-email.md`, `<framework>-patterns.md`) are project-specific and added by each downstream project as they accumulate ≥3 traceable rules per topic.

