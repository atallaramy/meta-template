---
description: Start work on a ticket — move backlog→active, set status, create branches in the listed sub-repos
argument-hint: <TICKET-ID>
---

# /ticket-start $ARGUMENTS

Start work on ticket `$ARGUMENTS`. Rules: GOVERNANCE §4 (folder=status), §7 (branch naming), §5 (`repos:` field).

## Procedure

1. **Locate.** Glob `meta/tickets/backlog/$ARGUMENTS-*.md`. If 0 matches → error "ticket not in backlog". If >1 → error (duplicate ID — validator should have caught this).
2. **Read frontmatter.** Must have `status: backlog`. Capture `repos:` list and the filename slug.
3. **Pre-flight.** Confirm working tree clean in every repo listed in `repos:` (run `git status --porcelain` in each). If any dirty → ask the user before proceeding.
   - **Queue gate (GOVERNANCE §19.7):** if the ticket is P2/P3 and `ROADMAP.md`'s Execution queue has an unstarted item, refuse — unless the owner overrides, and record the override with its one-line reason.
4. **Transition status.**
   - `cd meta && git mv tickets/backlog/$ARGUMENTS-<slug>.md tickets/active/`
   - Edit frontmatter: `status: active`, bump `updated:` to today's date.
   - If `branch:` is `null`, set it to `feat/$ARGUMENTS-<slug>` (lowercased ID + slug from filename).
5. **Create branches.** For each repo in `repos:`:
   - `cd <repo> && git fetch origin && git checkout <base> && git pull --ff-only && git checkout -b feat/$ARGUMENTS-<slug>`
   - (`<base>` = the configured base branch, e.g. `develop` or `main`.)
   - If the branch already exists, checkout without `-b` and report.
6. **Regenerate INDEX.** `cd meta && python3 scripts/build_index.py`
7. **Validate.** `python3 scripts/build_index.py --validate`. If errors → stop and surface.
8. **Report** in one block:
   - Ticket path
   - Branch name
   - Which sub-repos are now on that branch
   - Current `next_action:` if set (may be null; `/ticket-pause` will fill it)

## Guard rails

- Never force-push, never `git reset --hard`.
- If the user is already on a different feature branch in any sub-repo, stop and ask — don't stash or clobber.
- If `repos:` is empty, warn the user — the ticket should declare which sub-repos it touches (see GOVERNANCE §5).
