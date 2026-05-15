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

### 2026-05-11 — Auto-unblock dependent tickets when blocker ships (`scripts/build_index.py` `--fix` mode)

- **Scope of the port:** new `--fix` mode in `scripts/build_index.py` — detects stale `blocked_by:` entries (refs to tickets in `tickets/done/`), surgically rewrites the dependent's `blocked_by:` and `updated:` frontmatter lines via anchored regex (no YAML round-trip, no external deps), backs up + writes + re-parses to confirm `id/epic/status` round-trip identically, restores from backup on any drift, auto-stages touched files via `git add` with post-stage `git diff --cached` cross-check. `--validate` extended to report stale entries as errors. `--fix` is mutually exclusive with `--validate` AND `--check`. Plain mode warns about stale entries without failing. `_detect_multiline_list_fields()` enforces bracket-list form repo-wide (silent-parse footgun fix).
- **Companion changes (same migration):**
  - `.pre-commit-config.yaml` — replaced `--validate` + `--check` hook pair with a single `--fix` hook that does both internally + auto-stages.
  - CI workflow stays unchanged — still calls `--validate` + `--check` (defense in depth against `--no-verify` / external edits / force-pushes).
- **Why universal:** the auto-unblock pattern is pure ticket-system hygiene — works for any project using the meta template's ticket structure. Zero brand references.

---

### 2026-05-11 — Split flat best-practices.md into topic folder + wire agent Step 0

- **From:** `guidelines/best-practices.md`
- **To:** `guidelines/best-practices/overview.md` (folder)
- **Reason:** Flat-file format doesn't scale once a project accumulates project-specific learnings beyond the generic baseline. New folder layout: `core-loop.md` (rule #0 — write → review → community-check → loop), `overview.md` (cross-stack baseline — content unchanged, moved via `git mv`), plus topic files projects add as they learn (`cutover-patterns.md`, `dns-and-email.md`, `<framework>-patterns.md`, etc.).
- **Companion changes (same migration):**
  - `claude-config/agents/best-practices.md` — added Step 0 to Research Process: read `meta/guidelines/best-practices/*.md` first, `core-loop.md` first within that. Principles section reordered to put folder first.
  - `claude-config/CLAUDE.md` — "Pre-commit review gate" line replaced with "The Core Loop is rule #0" pointing at the new file; Guidelines section repointed at the folder.
- **Scope of the port:** universal pieces only — `core-loop.md`, `README.md` (with format spec + suggested topic-file names), `overview.md` move, agent Step 0 wire, CLAUDE.md rule. Any topic files (e.g. `cutover-patterns.md`, `dns-and-email.md`, `<framework>-patterns.md`) are project-specific and added by each downstream project as they accumulate ≥3 traceable rules per topic.

---

### 2026-05-15 — Sub-task IDs flattened (Jira-style); `<N>.<M>` decimal form deprecated for new tickets

- **What changed:** sub-tasks now use flat next-available IDs (e.g. `EPIC-8` as a child of `EPIC-7`), with the parent/child relationship encoded only in the `parent:` / `children:` frontmatter fields. The `<EPIC>-<N>.<M>` decimal form is **deprecated for new tickets**.
- **Why universal:** decimal IDs (`EPIC-7.1`) read like version labels, not child references; flat IDs match the conventions used by Jira, Linear, GitHub Issues, and other common issue trackers. The parent/child relationship is already expressed by the `parent:` / `children:` fields — encoding it in the ID is redundant and harder to scan. Convention applies to every project using this template.
- **Backwards compatibility:** existing `.M` IDs in any downstream project are NOT renamed (IDs are immutable per GOVERNANCE §2). The validator regex (`^([A-Z]{2,8}-\d+(\.\d+)?|HF-...)$`) continues to accept the `.M` form so historical tickets remain valid; no validator change required.
- **Files updated in the template:**
  - `GOVERNANCE.md` §1: sub-task filename pattern row → flat ID, relationship in frontmatter.
  - `GOVERNANCE.md` §2: ID format text updated, `.M` form explicitly marked deprecated-for-new-tickets, regex annotated.
  - `GOVERNANCE.md` §7: branch naming row for sub-task updated to same shape as story.
  - `GOVERNANCE.md` §9: injection decision tree updated to instruct new flat-ID + `parent:` / `children:` wiring instead of `EPIC-N.M`.
- **No file moves:** purely a forward-looking convention; no existing ticket renamed or relocated. Downstream projects inherit this on next template sync.

