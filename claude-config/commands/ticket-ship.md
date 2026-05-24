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
6. **Cross-reference compliance + product-strategy ledgers (if your project has them).** Ask the user, in one bundled turn:
   - **Compliance checklist.** If your project tracks compliance (SOC2, HIPAA, ISO27001, etc.) in `meta/compliance/<file>.md`, ask: "Does this ticket complete any items in the compliance checklist? List the line(s) or section IDs." **HARD GATE — do NOT touch the checklist file without an explicit, line-by-line user 'go'.** Compliance checklists are audit ledgers; silent ticks destroy traceability. On explicit go: tick the listed box(es) and append a short implementation-note pointing at this ticket. On "no" / "skip" / silence → leave the file alone and note `compliance: none` in the ship commit body so the skip is traceable.
   - **Product-strategy / production-readiness doc.** If your project tracks product strategy or production-readiness in a sibling repo, ask: "Does that doc need updating? (gates decided, bucket counts shifted, ticket moved between buckets, gate ticked, timeline revised?)" If yes, edit per user direction in that repo and commit + push there separately. If no, note the skip in the ship commit body.
   - Both edits happen BEFORE the meta commit so the checklist tick rides in the same ship-close action. The sibling-repo commit is referenced in the meta ship commit body if it happened.
7. **Regen INDEX.** `python scripts/build_index.py`
8. **Validate.** `python scripts/build_index.py --validate` — must pass. Folder/status match (`done/` + `status: done`) is enforced.
9. **Commit automatically.** Shipping IS the commit — no second roundtrip. Run as one shell sequence:
   ```bash
   cd meta && \
     git add tickets/active/$ARGUMENTS-*.md tickets/done/$ARGUMENTS-*.md \
             INDEX.md INDEX.json PROD-READINESS.md FEATURES.md \
             compliance/ 2>/dev/null; \
     git add tickets/backlog/  # any spawned follow-up tickets
     git commit -m "$(cat <<'EOF'
   chore(meta): ship $ARGUMENTS — <one-line capability or "control hardening" summary>

   <2-4 lines pulled from the Retrospective §What actually shipped: PR
   URLs / squash SHAs across the touched sub-repos + the headline change.>

   compliance: <ticked-line-IDs | none>
   <sibling-doc>: <sibling-SHA | no-change>
   EOF
   )"
   ```
   If the pre-commit hooks fail, fix the surfaced issue, re-stage, create a NEW commit (never `--amend`).

10. **Publish per your meta-repo policy.** Push (or open a PR) according to your project's convention — direct push to the meta repo's main branch if allowed, otherwise open a PR. Document the chosen policy in your project's `CLAUDE.md` so this step is unambiguous. NEVER force-push.

11. **Report:**
    - Ticket moved + committed: `active/$ARGUMENTS-<slug>.md` → `done/`
    - Meta commit SHA + publish result (push SHA or PR URL, per policy)
    - FEATURES.md row appended (or skipped — one-line justification)
    - Compliance checklist: lines ticked (with IDs) or `none`
    - Sibling business/strategy doc: sibling commit SHA or `no-change`
    - Any follow-up tickets created (with IDs)

## Guard rails

- **Auto-commit is the default.** Shipping is a single user action; breaking it into ship + commit is friction without value. Publishing (push vs. PR) follows your meta-repo policy — document it in `CLAUDE.md`.
- **Never delete branches.** The actual feature branches live in sub-repos; branch cleanup is a separate concern handled by the `committer` agent after PR merge, not this skill.
- **Never re-write existing Retrospective content.** If the section is already populated, append below existing text with a dated header — don't overwrite.
- **Validate before committing.** If the validator fails after the move (e.g. status/folder mismatch), stop and surface the error — do not commit a broken state.
- **Never force-push.** If push is rejected, rebase against the base branch and retry; if rebase has conflicts, stop and surface.
- **Never bypass hooks.** No `--no-verify`. Pre-commit hooks must pass; on failure, fix root cause + new commit.
