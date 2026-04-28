# Agent Team — generic seed

These are stack-agnostic agents shipped with the meta template. Add stack-specific agents (linters, testers, debuggers for your specific tech) as you build them out.

## Workflow Agents

| Agent | Purpose | Model |
|-------|---------|-------|
| `committer` | Conventional commits with approval workflow + PR/merge lifecycle | sonnet |
| `planner` | Complex feature plans, creates tickets in `meta/tickets/backlog/` per GOVERNANCE | opus |

## Analysis Agents

| Agent | Purpose | Model |
|-------|---------|-------|
| `analyzer` | Code analysis + git log patterns; information hub for cross-repo work | opus |
| `structure` | Bird's-eye view of the project across all sub-repos and shared contracts | opus |
| `researcher` | Internet-only research: official docs, community practices, RFCs | opus |
| `best-practices` | Codebase patterns + internet best practices combined | opus |

## Adding stack-specific agents

When your project picks a tech stack, add agents like:

- `<stack>-linter` — runs the linter for that stack (Ruff, ESLint, terraform fmt, etc.)
- `<stack>-tester` — runs the test suite for that stack (pytest, vitest, go test, etc.)
- `<stack>-debugger` — reads logs, identifies errors for that stack
- `<stack>-discovery` — maps the layout of that part of the codebase

Use the existing generic agents as the structural template. Each agent file:

```yaml
---
name: agent-name
description: >
  One-paragraph description of when to use this agent proactively.
tools:
  - Read
  - Grep
  - Bash
model: sonnet  # or opus for harder reasoning
---

(body — role, principles, definition of done)
```

## Agent Principles

All agents follow these rules:

- **Short, clear output** — no verbose explanations
- **Fix root causes** — no workarounds
- **Read before suggesting** — analyze actual code
- **Delete unused code boldly** — remove dead code without hesitation
- **Definition of Done** — each agent has explicit completion criteria

## Git workflow (committer agent)

Every git action requires explicit approval:

1. Stage files — requires approval
2. Commit — requires approval
3. Push — requires approval
4. Open PR — requires approval
5. Merge PR — requires approval (after CI passes)

No exceptions. No auto-commits.
