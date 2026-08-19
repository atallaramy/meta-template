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
- **The Core Loop is rule #0.** See `meta/guidelines/best-practices/core-loop.md`. Every unit of work iterates: write → code-review agent → security-review agent + manual `meta/guidelines/security-guidelines.md` pass → compliance lens (if your project has a regime) → `best-practices`/`researcher` community check → **fix everything the reviewers surface INSIDE THE DIFF — no deferrals**; a finding **outside the diff** is filed to `backlog/` **born P3** — recorded, promised to no one (GOVERNANCE §9.3); it earns P2 only with one line naming who is hurt and when (validator-enforced), P0/P1 need §19.4 triggers as fact, and **a ticket may not queue its own children** — it **does not interrupt**: P0 interrupts, P1 becomes next, only the owner promotes. Leftovers at ship time: small → finish before shipping; big → its own ticket at whatever the triggers say (a remainder is a smell of an over-scoped cut) → loop until a pass surfaces zero new **in-diff** findings, **maximum two passes**. THEN commit. Runs on top of language linters. **No compromises. No skipping. No "small change exemption."**
- **Brief the reviewers on the DIFF, not the system — and fix the diff's boundary BEFORE you start.** Name the files + acceptance criteria in the ticket first; anything found outside them is out-of-diff and gets filed, not fixed, unless the owner widens the ticket. Both halves matter: pointing the agents at the whole system is what generates the findings, and an unfixed boundary lets "in-diff" stretch mid-flight to swallow whatever is more interesting than the gate. (Measured in a source project: every ticket created over an 11-day stretch came from reviewing prior work — zero from a customer, the roadmap, or the business plan. GOVERNANCE §19.8.)

## Session Start

- Read `meta/STATUS.md` for current project state
- Read `meta/ROADMAP.md` — find `>>> CURRENT <<<` marker for active focus
- Read `meta/GOVERNANCE.md` — ticket system rules, epic registry, archival rules, never-delete rule
- Consult `meta/INDEX.md` (or `meta/INDEX.json` for scripted queries) for full ticket list
- For any **active** ticket you're resuming, read its `next_action:` field first — that's the session-handoff pointer. Use `/ticket-resume <ID>` to re-hydrate cleanly.

## Session End / Hygiene (GOVERNANCE §15)

- **Merged work SHIPS, unfinished work pauses.** Code merged → `/ticket-ship` at the merge, in the same session. Not merged → `/ticket-pause` to write `next_action:` + stamp STATUS before ending. Without one of the two, the next session starts cold or `active/` goes stale (GOVERNANCE §15.1).
- **Decisions live in tickets, not in chat.** When you present 2–3 options and the user picks, offer `/decide` before proceeding — capture options + pick + rationale into the ticket's Decisions section.
- **Rewrite `new_session` by OVERWRITING, never appending (GOVERNANCE §20).** It lives at `meta/new_session.md` (tracked; symlinked to the project root as `new_session`). Fixed shape: `Boot` / `First message` / `Which ticket` stay verbatim; `Where we got to` (**max 3 sessions**) / `This session` / `State` are overwritten. Size-capped by `build_index.py` + CI. **Do not summarise tickets into it** — a trap's home is its own ticket's `## Context` / `## Plan` step 0; a summary of N tickets is a second copy that drifts.

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

- IDs immutable once assigned (e.g. `EX-1`, `EX-2`)
- Folder = status (`tickets/{active,backlog,blocked,parked,done}/`). `parked/` = externally-gated; each ticket carries `parked_until:` naming the trigger. See GOVERNANCE.md §4–§5.
- **Every ticket is prioritised at filing time** (GOVERNANCE §9.3 + §19): spawned (`discovered_from` set) → born **P3**; root (customer/roadmap/plan) → **P2**; P0/P1 need a §19.4 trigger as fact in `priority_because` + owner confirmation. P0 interrupts, P1 becomes next, P2/P3 wait.
- **The ROADMAP Execution queue is the promise list** — capped at 7 live items (GOVERNANCE §9.2). Everything else lives in `INDEX.md` only. Propose a slot via `proposed_priority:`; silence = not yet, and `build_index.py --health` resurfaces every unanswered proposal.
- **Never `rm` files** — move to `meta/_archive/` with a MIGRATION-LOG entry
- New ticket: copy `meta/templates/TICKET.md`, fill frontmatter, land in `meta/tickets/backlog/`

## Guidelines

- `meta/guidelines/best-practices/` — **project-specific** best practices (topic-partitioned: `core-loop.md` as rule #0, `overview.md` as cross-stack baseline, plus topic files added per project). **Read first** before writing new code — the `best-practices` agent is wired to consult this folder before codebase/internet.
- `meta/guidelines/security-guidelines.md` — auth, crypto, cookies, audit logging
- `meta/guidelines/implementation-checklists.md` — pre-flight for complex features
- `meta/guidelines/design-system.md` — frontend design system + component standards

## Project-specific section

*(Replace this section with anything unique to your project: tech stack, env-specific rules, deployment quirks, naming conventions. The sections above are universal — this is where project-specific rules go.)*
