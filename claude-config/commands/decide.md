---
description: Capture an architectural decision into the active ticket's Decisions section — options, pick, rationale
argument-hint: [<TICKET-ID>]
---

# /decide $ARGUMENTS

Append a decision entry to the active ticket's Decisions section. Rule: GOVERNANCE §15.2 (decisions live in tickets, not in chat).

## Procedure

1. **Identify the ticket.**
   - If `$ARGUMENTS` given → use `meta/tickets/active/$ARGUMENTS-*.md`.
   - Else → find the single active ticket, or ask if there are multiple.
2. **Gather the decision from context.** If the user just picked between options you offered, you already have:
   - **Options** — the 2–3 alternatives you presented
   - **Pick** — the one the user chose
   - **Why** — the user's (or your) rationale
   If any is unclear, ask concisely. One short turn max.
3. **Append to the ticket's `## Decisions` section** (template puts this between `Risks` and `Retrospective`). Format:
   ```markdown
   ### YYYY-MM-DD — <short title of the decision>
   - **Options:** (a) option one, (b) option two, (c) option three
   - **Pick:** (b) option two
   - **Why:** one or two sentences — the actual reasoning
   ```
4. **Bump `updated:`** in frontmatter to today.
5. **Regen INDEX.** `cd meta && python scripts/build_index.py`
6. **Report** the entry that was written.

## When to use

- **Always** after the user picks between options you presented on a material choice (architecture, library, API shape, data model).
- **Skip** for trivial picks (variable names, formatting, file layout).
- A good test: "would future-me, looking at this ticket 6 months later, need to know why?"

## Guard rails

- Never rewrite past Decisions entries. Only append.
- Never invent options or rationales the user didn't say. If unclear, ask before writing.
