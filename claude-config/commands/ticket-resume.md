---
description: Resume an active ticket — read next_action, show branch state, prime context for the session
argument-hint: <TICKET-ID>
---

# /ticket-resume $ARGUMENTS

Re-hydrate context for ticket `$ARGUMENTS`. Inverse of `/ticket-pause`.

## Procedure

1. **Locate.** Find `meta/tickets/active/$ARGUMENTS-*.md`. If not found:
   - Check `backlog/` → ticket is ready but not started; suggest `/ticket-start $ARGUMENTS`.
   - Check `parked/` → ticket is gated by an external trigger. Read its `parked_until:` and report: "ticket `$ARGUMENTS` is parked until `<trigger>`; activate by moving to `backlog/`, clearing `parked_until:`, and assigning a `priority:` (§19 — parked tickets carry none, backlog tickets must), then re-run." Do NOT auto-unpark.
   - Check `blocked/` → ticket is waiting on an internal dependency; report the `blocked_by:` list.
   - Check `done/` → ticket has shipped; suggest reading its retrospective.
2. **Read the ticket.**
   - Extract: `title`, `next_action:`, `repos:`, `branch:`.
   - Skim the body: last modified Plan section, last Decisions entry, any open Risks.
3. **Check branch state per repo.** For each repo in `repos:`:
   - Current branch (should match `branch:` field). If mismatch → report "repo X is on `<other>`, expected `<branch>`".
   - `git status --porcelain` — any uncommitted changes?
   - `git log --oneline <base>..HEAD -n 5` — last few commits on this branch.
   - Is the branch up to date with `origin/<base>`?
4. **Report a concise re-hydration block:**
   ```
   Ticket: <ID> — <title>
   Next action: <next_action>

   Branches:
     repo-1: feat/<ID>-<slug>  [3 commits ahead, clean]
     repo-2: feat/<ID>-<slug>  [not yet checked out — run `git checkout`]

   Last commits (repo-1):
     abc123 feat: phase 2 API client
     def456 test: coverage for phase 2

   Recent Decisions: <date> — <title>
   Open risks: none / <list>
   ```
5. **Do NOT modify anything.** Resume is read-only. If the user wants to check out a missing branch, tell them the command — don't auto-run.

## Guard rails

- No git fetch, no pull, no checkout — resume is strictly read-only.
- If `next_action:` is null or empty on an active ticket, flag it as a bug (validator should have caught it) and stop.
