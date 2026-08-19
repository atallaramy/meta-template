---
description: Pause work on the active ticket — write next_action, stamp STATUS.md, regen INDEX. No WIP commit.
argument-hint: [<TICKET-ID>]
---

# /ticket-pause $ARGUMENTS

Pause the currently active ticket (or the one passed as `$ARGUMENTS` if given). Rule: GOVERNANCE §15.1 — **merged work SHIPS (`/ticket-ship` at the merge); only unfinished work pauses.** Never pause a ticket whose code has already landed.

## Procedure

1. **Identify the ticket.**
   - If `$ARGUMENTS` given → use `meta/tickets/active/$ARGUMENTS-*.md`.
   - Else → list all files in `meta/tickets/active/`. If exactly 1 → use it. If >1 → ask the user which.
2. **Gather `next_action:`.**
   - Ask the user: "One sentence — what's the next concrete step?"
   - Validate: non-empty, imperative mood, concrete. ✅ `Run phase 3 smoke tests`. ❌ `Continue`, `Work on this more`, `null`.
3. **Update ticket frontmatter.**
   - Set `next_action: <the sentence>`.
   - Bump `updated:` to today's date.
4. **Stamp STATUS.md.**
   - OVERWRITE the `## Current State` block with the current snapshot (GOVERNANCE §18 — never append a dated line; the size cap refuses the commit if you do).
5. **Regen INDEX.** `cd meta && python3 scripts/build_index.py`
6. **Validate.** `python3 scripts/build_index.py --validate`. Must pass — `next_action` is required on active tickets.
7. **Report:**
   - Ticket ID + `next_action:` written
   - STATUS line added
   - **Reminder:** no WIP commit was made. If switching machines, consider `git stash push -m "WIP $ARGUMENTS"` or a manual commit before ending.

## Guard rails

- Do NOT commit or push anything. Pause is a **bookmark**, not a checkpoint.
- Do NOT change `status:` — the ticket stays `active`. It's still in flight, just bookmarked.
- If the ticket's code has MERGED, refuse to pause — run `/ticket-ship` instead (GOVERNANCE §15.1).
- If the user refuses to give a `next_action`, explain why it's required (GOVERNANCE §15.1) and ask again. Do not write `next_action: null` on an active ticket.
