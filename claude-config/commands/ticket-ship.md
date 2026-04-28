---
description: Finalize a shipped ticket — fill retrospective, move active→done, append to FEATURES.md, regen INDEX
argument-hint: <TICKET-ID>
---

# /ticket-ship $ARGUMENTS

Finalize ticket `$ARGUMENTS` as shipped. Moves it from `active/` to `done/`, fills the Retrospective, appends one line to `FEATURES.md`. Rules: GOVERNANCE §4 (folder=status), §13 (ticket structure — plan + retro in one file).

## Pre-flight checks (stop and surface to user on any failure)

1. **Located.** Ticket must be at `meta/tickets/active/$ARGUMENTS-*.md`. If not there → stop.
2. **Acceptance criteria.** Read the ticket's `## Acceptance criteria` section. Every checkbox must be `[x]`. If any are `[ ]` → print the unchecked items and ask the user: "these aren't checked — ship anyway?" Do not proceed without explicit yes.
3. **Plan items.** Read `## Plan`. Same check — warn (don't block) on unchecked items.
4. **Merged branch.** Read `branch:` from frontmatter. For each repo in `repos:`:
   - `git fetch origin` then `git log origin/<base> ^origin/<branch>` — if the branch has commits NOT on `<base>`, warn: "branch has unmerged commits — ship anyway?"
   - If the branch already deleted on remote and last commits are on `<base>`, that's fine.

## Procedure

1. **Gather retrospective inputs from the user** (one short turn each, can be done in bulk):
   - **What actually shipped:** PR URLs and/or key commit SHAs across the `repos:` listed.
   - **Deviations from plan:** what changed during execution and why (or "none").
   - **Lessons / follow-up tickets:** anything worth capturing. If follow-ups exist → create them in `backlog/` with `discovered_from: $ARGUMENTS`.
2. **Fill the Retrospective section** of the ticket with the three sub-sections from the template (`## Retrospective` → `### What actually shipped` / `### Deviations from plan` / `### Lessons / follow-ups`). Append, don't overwrite.
3. **Update frontmatter:**
   - `status: done`
   - bump `updated:` to today's date
   - clear `next_action:` to `null` (ticket is done — no next action)
4. **Move the file.** `cd meta && git mv tickets/active/$ARGUMENTS-<slug>.md tickets/done/`
5. **Append to FEATURES.md.** One row, today's date, one-line feature description pulled from ticket title/retrospective, `scope` column lists the `repos:` touched.
   ```
   | YYYY-MM-DD | <one-line feature description> | <comma-separated repos> |
   ```
6. **Regen INDEX.** `python scripts/build_index.py`
7. **Validate.** `python scripts/build_index.py --validate` — must pass. Folder/status match (`done/` + `status: done`) is enforced.
8. **Report:**
   - Ticket moved: `active/$ARGUMENTS-<slug>.md` → `done/`
   - FEATURES.md row appended
   - Any follow-up tickets created (with IDs)
   - Reminder: commit the move + FEATURES update in a single `chore(meta): ship $ARGUMENTS` commit.

## Guard rails

- **Never auto-commit.** Leave everything staged or unstaged — user commits when ready.
- **Never delete branches.** The actual feature branches live in sub-repos; branch cleanup is a separate concern handled by the `committer` agent after PR merge, not this skill.
- **Never re-write existing Retrospective content.** If the section is already populated, append below existing text with a dated header — don't overwrite.
- **Validate before finishing.** If the validator fails after the move (e.g. status/folder mismatch), stop and surface the error — do not leave the repo in a broken state.
