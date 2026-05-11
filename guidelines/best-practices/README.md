# Project-specific best practices

> **Read first.** The `best-practices` agent is wired to consult this folder before searching the codebase or the internet. Two kinds of content live here:
>
> - **`core-loop.md`** — rule #0 of the project (the foundational write → review → community-check → loop cycle). Read first, every time.
> - **`overview.md`** — generic cross-stack baseline (research-first, implementation plans, commits, code review, refactoring, decision-making, testing). The wide net.
> - **Topic files** (added per project as you accumulate them) — **hard-won, project-specific** rules. Patterns that future-you (or another agent) would *only* know by having lived through the original incident. This is what differentiates this folder from any generic best-practices reference on the internet.

## How this folder is used

1. The `best-practices` agent (`.claude/agents/best-practices.md`) runs **Step 0** of its Research Process before anything else: glob `meta/guidelines/best-practices/*.md`, read every matching file (`core-loop.md` first — it's rule #0), cite the relevant rule when answering.
2. The agent then falls back to its existing steps (codebase grep, internet search, framework / RFC / OWASP lookups). Folder rules **win ties** over generic advice — they're project-specific by definition.
3. Every entry is **traceable**: each rule cites a ticket ID, a memory file, or an incident postmortem. If you can't trace it, it doesn't belong here yet.

## When to add a new rule

A rule lands here when **all four** are true:

- It applies to *this* project specifically.
- A future agent would not derive it from the codebase or generic best-practice docs — it's a learned exception, gotcha, or sequencing rule.
- It came out of a real incident or shipped ticket — not speculation. Ticket ID or postmortem reference is the citation.
- Stating it as **Rule / Why / How to apply** would actually help (vs. a one-liner that's already obvious from the code).

## Suggested topic files (add as you accumulate ≥3 rules per topic)

Common topic-files projects grow into:

| File | Topic |
|---|---|
| `cutover-patterns.md` | Multi-step rollouts, branch freezes, soak gates, dual-write transitions, cross-repo coordination. |
| `dns-and-email.md` | DNS / mail / cert foot-guns specific to your stack. |
| `docker-and-ci.md` | Container / probe / CI mechanics; deprecation cadence; state-lock interactions. |
| `<framework>-patterns.md` | Framework-specific patterns (e.g. Django, Rails, Next.js, etc.) — ORM, auth, middleware, lifecycle. |
| `frontend-patterns.md` | Browser / cookie / hydration / Sentry-style patterns. |

Add only when you have a real cluster — empty seed files are noise.

## Format (every rule)

```markdown
### One-line rule name

**Rule:** What to do, imperative, one sentence.
**Why:** The incident or constraint that made this a rule. Cite ticket ID / postmortem.
**How to apply:** When / where this kicks in.
```

Three lines per rule, no exceptions. Long rationale belongs in the source ticket; this folder is the index.

## Cross-references

- **Security baseline:** `meta/guidelines/security-guidelines.md`.
- **Implementation checklists for complex features:** `meta/guidelines/implementation-checklists.md`.
- **Source tickets:** `meta/tickets/done/` — every rule here should cite at least one.
