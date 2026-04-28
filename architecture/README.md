# Architecture

> Living design docs — **not tickets**. Updated as the architecture evolves.

## What belongs here

- One document per major architectural concern: data model, multi-tenancy model, auth model, deployment topology, etc.
- Diagrams (text-first — Mermaid, ASCII; binary diagrams allowed but keep source).
- Trade-off discussions that survived multiple tickets.

## What does NOT belong here

- Per-ticket plans → ticket file
- Decisions made in flight → ticket Decisions section (graduated to architecture only when they become foundational)
- How-to walkthroughs → `guides/`

## Format

- Front matter at top: title, owner-epic, last-updated.
- Section headers consistent within a file.
- Diagrams co-located with the prose they support.

## Lifecycle

- New: a ticket with significant architectural impact promotes its design decisions here on ship.
- Update: subsequent tickets that change the architecture update the doc as part of their plan.
- Retire: when an architecture is replaced, archive the old doc to `_archive/` with a MIGRATION-LOG entry, and link from the new doc.
