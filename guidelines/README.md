# Guidelines

> Standards you must follow. One file per topic. Keep each file tight — link to deeper rationale in tickets.

## Files (template seeds — fill in for your project)

- `best-practices.md` — code quality, consistency, research-first patterns
- `security-guidelines.md` — auth, crypto, cookies, audit logging
- `design-system.md` — UX / frontend design system + component standards
- `implementation-checklists.md` — pre-flight for complex features

## How to use

- Reference these from tickets and code reviews ("see `guidelines/security-guidelines.md` §X").
- When a decision establishes a durable rule, add it here (not just in chat). See GOVERNANCE §14 (rule-capture principle).
- Keep style consistent within each file — match the prevailing density. Rationale belongs in the linked ticket, not here.

## What does NOT belong here

- Per-ticket plans → ticket file
- One-off decisions → MIGRATION-LOG or ticket Decisions section
- Architecture docs → `architecture/`
- Compliance evidence → `compliance/`
