# Project Guidelines

<!--
BACKUP COPY of the live CLAUDE.md that lives at the project root's
`.claude/CLAUDE.md`. The live file is what Claude Code actually reads;
this copy exists so the content is version-controlled in case the live
file is lost, corrupted, or reset by a fresh Claude Code install.

Keep in sync: when you edit `.claude/CLAUDE.md`, also update this file
(or vice versa).
-->

## Git Branch Workflow

- *(Document your branching model here. Common patterns: trunk-based, develop+main, GitHub Flow.)*
- Feature branches branch from `<base>`, PR back into `<base>` — never push directly to `<base>`.
- Git commit format: `type(scope): description` + blank line + body explaining **why**.
- **PR merge style:** *(squash, merge, or rebase — pick one and document it here)*.
- **Pre-commit review gate.** Before EVERY commit, run a code review on the staged diff (linter + reviewer). Fix all surfaced issues before committing — no "I'll fix in next commit" deferrals.

## Session Start

- Read `meta/STATUS.md` for current project state
- Read `meta/ROADMAP.md` — find `>>> CURRENT <<<` marker for active focus
- Read `meta/GOVERNANCE.md` — ticket system rules, epic registry, archival rules, never-delete rule
- Consult `meta/INDEX.md` (or `meta/INDEX.json` for scripted queries) for full ticket list
- For any **active** ticket you're resuming, read its `next_action:` field first — that's the session-handoff pointer. Use `/ticket-resume <ID>` to re-hydrate cleanly.

## Session End / Hygiene (GOVERNANCE §15)

- **Always pause before ending a session with an active ticket.** Run `/ticket-pause` to write `next_action:` + stamp STATUS. Without it, the next session starts cold.
- **Decisions live in tickets, not in chat.** When you present 2–3 options and the user picks, offer `/decide` before proceeding — capture options + pick + rationale into the ticket's Decisions section.

## Agent Dispatch

Specialized agents live in `.claude/agents/` (backed up at `meta/claude-config/agents/`). Generic agents shipped with the meta template:

| Task | Agent |
|------|-------|
| Commit, push, PR, merge | `committer` |
| Plan complex features (creates tickets) | `planner` |
| Analyze code, trace deps, cross-repo impacts | `analyzer` |
| Bird's-eye project map across all sub-repos | `structure` |
| Internet-only research (docs, articles) | `researcher` |
| Codebase + internet pattern verification | `best-practices` |

*(Add stack-specific agents below as you create them — linters, testers, debuggers for your stack.)*

## Decision Making

- No refactor later. Pick the future-proof path now.
- Think all flow paths — not just happy path.
- At architecture decision points: pause, show 2-3 options with tradeoffs, recommend one, ask.
- Fix root cause, not symptom. No workarounds.

## Before Writing Security Code

- Verify online first — research OWASP, RFCs, community patterns.
- Enumerate edge cases and attack vectors before implementation.
- See `meta/guidelines/security-guidelines.md` for coding standards.

## Communication Rules

- User's explicit instructions override carried context. If confused, ASK.
- Verify plan info matches actual code before making changes.

## Ticket system

All plans, tickets, architecture docs, audits, compliance checklists live in `meta/`. Rules in `meta/GOVERNANCE.md`:

- IDs immutable once assigned (e.g. `AUTH-1`, `EMAIL-2`)
- Folder = status (`tickets/{active,backlog,blocked,done}/`)
- **Never `rm` files** — move to `meta/_archive/` with a MIGRATION-LOG entry
- New ticket: copy `meta/templates/TICKET.md`, fill frontmatter, land in `meta/tickets/backlog/`

## Guidelines

- `meta/guidelines/best-practices.md` — code quality, consistency, research-first
- `meta/guidelines/security-guidelines.md` — auth, crypto, cookies, audit logging
- `meta/guidelines/implementation-checklists.md` — pre-flight for complex features
- `meta/guidelines/design-system.md` — frontend design system + component standards

## Project-specific section

*(Replace this section with anything unique to your project: tech stack, env-specific rules, deployment quirks, naming conventions. The sections above are universal — this is where project-specific rules go.)*
