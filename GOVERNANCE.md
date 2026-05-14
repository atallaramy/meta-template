# Ticket System Governance

**Owner:** this repo is the single source of truth for ticket system rules. No other file defines these rules.
**Applies to:** every ticket, epic, hotfix, architecture doc, and migration action in this repo.

---

## 1. Ticket types

| Type | What it is | Folder | Filename pattern |
|---|---|---|---|
| **Epic** | Domain-level capability charter (not a task — a scope definition) | `epics/` | `<CODE>.md` |
| **Story** | A concrete, shippable unit of work inside an epic | `tickets/{status}/` | `<CODE>-<N>-<slug>.md` |
| **Sub-task** | Optional split of a large story | `tickets/{status}/` | `<CODE>-<N>.<M>-<slug>.md` |
| **Hotfix** | Urgent, out-of-band fix. Date-stamped, not epic-numbered. | `hotfix/` | `HF-YYYY-MM-DD-<slug>.md` |

---

## 2. ID scheme

- Format: `<EPIC>-<N>` (story) or `<EPIC>-<N>.<M>` (sub-task) or `HF-YYYY-MM-DD-<slug>` (hotfix)
- `<EPIC>` is a code from the **Epic Registry** (section 3).
- `<N>` is the next available integer within that epic, **never recycled**.
- **IDs are immutable once assigned.** Filename slug can be renamed, folder can change (status transitions), but the `ID` field in frontmatter is permanent.
- **Retroactive numbering is chronological.** When assigning IDs to existing-but-unticketed work, number by the order the work actually shipped (earliest = N=1), not by file creation date. This keeps the ticket timeline aligned with the git history.
- **Regex:** `^([A-Z]{2,8}-\d+(\.\d+)?|HF-\d{4}-\d{2}-\d{2}-[a-z0-9-]+)$`

### Filename convention

- **Tickets:** `<ID>-<slug>.md` — e.g. `AUTH-1-login-flow.md`
- **Hotfixes:** `<ID>.md` — e.g. `HF-2026-04-18-broken-deploy.md` (ID already contains the slug)
- Slug rules: lowercase `[a-z0-9]`, hyphen-separated, no leading/trailing/double hyphens, non-empty.
- The `<ID>` portion of the filename **must equal** the `id:` field in frontmatter. Validator enforces this — prevents the filename and the referential ID from silently drifting apart when a file is copied or renamed by hand.
- Renaming the slug is allowed (e.g. title clarification); the `id:` stays frozen.

---

## 3. Epic Registry (open list)

The registry is **open** — add epics as your project grows. The seed below covers patterns common to most software projects; delete what you don't use, add what's missing. Each new epic should pass the add-epic gate (section 10) — that gate exists to keep boundaries clean, not to block additions.

| Code | Owns | Does NOT own |
|---|---|---|
| **AUTH** | Login, logout, sessions, passwords, MFA, SSO, password reset, token lifecycle | Permission/RBAC rules (→ SEC); user-profile data unrelated to identity (→ feature epic) |
| **INFRA** | Provisioning, networking, DNS, cloud resources, environments | CI/CD pipelines (→ CICD); observability stack itself (→ OBS) |
| **OBS** | Logging, metrics, tracing, error reporting, alerts, dashboards | Audit-log policy (→ SEC); per-feature instrumentation lives with the feature |
| **CICD** | Build pipelines, test runners, deploy automation | The application code being deployed |
| **SEC** | Security hardening cross-cutting AUTH/INFRA (CSP, headers, secrets, audit findings, RBAC) | Compliance evidence (→ `compliance/`); per-feature security work lives with the feature |
| **UX** | Design system, accessibility, internationalization, e2e UX testing | Per-feature screens (→ owning epic) |
| **API** | API versioning, contract testing, schema management | API endpoints themselves (→ the epic owning the feature) |
| **DX** | Developer experience: meta-repo tooling, AI agent definitions, slash commands, project-specific best-practices, governance evolution | Feature code; CI/CD pipelines (→ CICD); domain-specific guidelines owned by another epic |
| **DOCS** | User-facing docs, READMEs, runbooks, public API references | Internal architecture docs (→ `architecture/`); per-ticket plans (→ ticket file) |

### Suggested-but-unseeded codes

Add when you need them: `DATA` (data model, migrations, ETL), `BILLING`, `EMAIL`, `TENANCY` (multi-tenancy), `COMPL` (compliance work), `PERF` (performance). Adding a new code requires the add-epic gate (section 10).

### Synonym aliases (DO NOT create as epic codes)

- `AUTHZ`, `AUTHN`, `AUTHORISATION`, `AUTHORIZATION`, `IDENTITY` → use **AUTH**
- `MONITORING`, `LOGGING`, `TELEMETRY` → use **OBS**
- `DEPLOY`, `DEPLOYMENT`, `BUILD` → use **CICD**
- `FRONTEND`, `DESIGN`, `A11Y`, `I18N` → use **UX**
- `DEVEX`, `DEVEXP`, `DEV-EXPERIENCE`, `TOOLING`, `META`, `AGENTS`, `SKILLS` → use **DX**
- `DOCUMENTATION`, `DOC`, `README`, `RUNBOOK` → use **DOCS**

### Selection algorithm

Follow this procedure. Do not reason from scratch each time.

1. **One-sentence scope.** State the work item in one sentence: "this ticket does X."
2. **Scan `Owns` lines** in the registry above. For each epic, ask: "does my one-sentence scope match this `Owns` line?"
3. **Count matches:**
   - **0 matches** → work may not fit any epic. Re-read. If still 0, go to the add-epic gate (section 10). Do NOT create the ticket until resolved.
   - **exactly 1 match** → pick it. Done.
   - **2 or more matches** → go to step 4.
4. **Multi-match disambiguation.** Open each candidate epic's charter (`epics/<CODE>.md`). Read its `Does NOT own` list. Most items land cleanly in exactly one epic after this check.
5. **Still tied?** Pick the epic whose **business outcome** this ticket serves, not the mechanism.
6. **Not confident?** → **ASK THE USER.** Present the 2 candidate epics with a one-line rationale each, recommend one, ask. Do NOT guess silently. After the user answers, add the resolved case to the Disambiguation Examples table so future you doesn't have to ask again.
7. **Impossible to pick even after asking?** The epic boundaries are wrong for this work. Open a PR on this file to clarify `Owns` / `Does NOT own`; do NOT create the ticket until the PR merges.

### Disambiguation examples

*(Living table. Every resolved ambiguity becomes a future shortcut. Add a row when you ask the user a borderline question.)*

| Work | Epic | Why (the rule that decides) |
|---|---|---|
| Password strength increase | **AUTH** | Password policy is AUTH's; SEC audits, AUTH implements. |
| CSP header change | **SEC** | Security posture is cross-cutting; SEC is the epic for that. |
| Rate-limiting class for a specific endpoint | **<owning-epic>** | SEC owns the *policy*; the implementation lives with the feature. |
| Log retention policy | **OBS** | Retention is a logging-pipeline concern. |
| API versioning strategy (v1 → v2) | **API** | Versioning contract is API's charter. |

---

## 4. Lifecycle (folder = status)

```
tickets/
├── backlog/     # identified, ready to pick up
├── active/      # in progress on a branch
├── blocked/     # cannot proceed (frontmatter must state blocked_by — internal dependency)
├── parked/      # gated by an external trigger (audit date, launch date, calendar event); not yet startable
└── done/        # shipped and verified
```

Transitions are `git mv` operations. The frontmatter `status:` field must match the folder name at all times — the linter enforces this.

### `blocked` vs `parked` — semantic distinction

- **`blocked`** — waiting on **another ticket** (internal dependency). The blocker is a ticket ID; frontmatter `blocked_by:` lists it. Stale entries are auto-cleared by `scripts/build_index.py --fix` when the blocker moves to `done/`.
- **`parked`** — waiting on an **external trigger** (audit window, launch date, calendar event, business decision). The trigger is a named event; frontmatter `parked_until:` names it. Activation requires a human + `git mv` back to `backlog/`.

If you find yourself wanting to write `blocked_by: [external-event]`, the ticket belongs in `parked/` instead.

---

## 5. Frontmatter schema

Required on every ticket file:

```yaml
---
id: AUTH-1                           # immutable once assigned
title: Login flow
epic: AUTH                           # must match epic registry
status: active                       # backlog | active | blocked | parked | done
created: 2026-01-15                  # ISO date, set once
updated: 2026-01-15                  # bumped on significant edits
parent: null                         # or another ticket ID
children: []                         # list of ticket IDs
blocks: []                           # list of ticket IDs this ticket blocks
blocked_by: []                       # list of ticket IDs blocking this ticket
discovered_from: null                # ticket ID that caused this ticket to be created
branch: feat/AUTH-1-login-flow       # or null
repos: []                            # sub-repos this ticket touches; free-form (configure VALID_REPOS in scripts/build_index.py if you want enforcement)
next_action: Run smoke tests.        # one sentence; required when status == active
parked_until: null                   # required when status == parked; names the external trigger
---
```

### `next_action:` — the session-handoff field

- **Purpose:** carry context across AI sessions. Written at `/ticket-pause`, read at `/ticket-resume`.
- **Required** when `status: active` (validator enforces). Free-form on other statuses.
- **Format:** one sentence, imperative mood, concrete. ✅ `Run phase-0 preflight checks`. ❌ `Continue work`.

### `parked_until:` — the activation-trigger field

- **Purpose:** name the external event that, when it fires, moves this ticket back to `backlog/`. Without this field, parked tickets become invisible technical debt — nobody remembers why they're parked or when to unpark.
- **Required** when `status: parked` (validator enforces). Free-form on other statuses (typically `null`).
- **Format:** short string. Suggested shapes:
  - A named project event (e.g. `prod-cutover`, `compliance-audit`, `beta-launch`, `v2-release`)
  - An explicit calendar date when known: `<YYYY-MM-DD>` (e.g. `2026-09-01`)
  - A descriptor pointing at another condition (e.g. `after-AUTH-7-ships`, `first-enterprise-customer`)
- **Single trigger per ticket:** if multiple triggers could activate the ticket, pick the **earliest realistic** one. Document the canonical trigger names somewhere stable in your project (a `READINESS.md` doc, or this file) so naming stays consistent — tickets reference these names; one source of truth keeps drift out.
- **Why parked, not blocked:** `blocked` is for internal dependencies (another ticket); `parked` is for external events. See §4 "blocked vs parked" semantic distinction.

### `repos:` — which sub-repos the ticket touches

- **Values:** any repo names you use. Configure the allow-list in `scripts/build_index.py` (`VALID_REPOS`) if you want validation; otherwise leave it empty for free-form.
- **Used by** `/ticket-start` to know where to create the feature branch. A ticket with `repos: [backend, frontend]` gets a branch in both.

---

## 6. Archival rules — **NEVER DELETE FILES**

**Rule:** once a file has existed in this repo, it is never `rm`'d. Move to `_archive/` instead.

| Scenario | Action |
|---|---|
| Ticket shipped and retrospective written | move to `tickets/done/` (this IS the archive for shipped work) |
| Plan superseded by a better plan | move the old plan to `_archive/` with MIGRATION-LOG entry referencing its successor |
| File's purpose is unknown / uncertain relevance | move to `_archive/` with note "relevance uncertain as of <date>" |
| Index/README rendered obsolete by INDEX.md | move to `_archive/` (don't delete — it may have context INDEX.md lacks) |
| Backup or draft that was never promoted | move to `_archive/` |

**Why:** audit trail. Future-you (or an auditor) asks "what happened to document X?" — `_archive/` answers with the original content. Deletion destroys that trail for zero storage savings.

**Exceptions:** none. If you think you have a reason to delete, write the reason in MIGRATION-LOG instead and archive.

### Archive-when-uncertain sub-rule

If a file's relevance is uncertain — either because it's old and you don't remember, or because the described issue may have been fixed — **archive it with a note**, don't create a ticket asserting the issue is still real. Promote from archive to a real ticket only after verifying the underlying issue still exists.

Note format in MIGRATION-LOG (or adjacent log):
> `<path>` → `_archive/...` — relevance unverified as of `<date>`; verify `<specific thing to check>` before acting; promote to ticket only after confirming issue persists.

---

## 7. Branch naming

| Work type | Branch pattern |
|---|---|
| Story | `feat/<EPIC>-<N>-<slug>` e.g. `feat/AUTH-1-login-flow` |
| Sub-task of a story | `feat/<EPIC>-<N>.<M>-<slug>` |
| Hotfix | `hotfix/HF-<date>-<slug>` |
| Refactor with no feature change | `chore/<EPIC>-<N>-<slug>` |

---

## 8. Commit / PR rules

- Commit subject: `type(scope): description (TICKET-ID)` — ticket ID at end. Example: `feat(auth): add password strength meter (AUTH-3)`
- PR title: `<TICKET-ID>: <short summary>`
- PR body: link to the ticket file (`tickets/active/<file>.md`)
- PRs that touch multiple tickets: list all IDs in the body, primary ID in title.

---

## 9. Injection (new work appearing mid-flight)

**Decision tree:**

```
Is it urgent + small + out-of-band?
├── YES → hotfix (date-stamped file in hotfix/, own branch)
└── NO  → Is it needed to complete the current ticket?
         ├── YES → sub-task of current ticket (EPIC-N.M)
         └── NO  → new story (EPIC-M) — set `discovered_from` to current ticket
                    ├── blocks current ticket? move current to blocked/, add blocked_by
                    └── doesn't block? current continues; new story enters backlog/
```

---

## 10. Add-epic gate

Adding a new epic code requires:

1. PR edits section 3 (Epic Registry)
2. Justify: why doesn't this fit an existing epic?
3. State scope: includes X, excludes Y (belongs to Z)
4. Log entry in MIGRATION-LOG.md under "Epic additions"
5. Synonym table updated to block any likely alias

If the tension is "X could be epic A or epic B" — fix the boundaries of A and B, don't create epic C.

---

## 11. INDEX.md regeneration

- Auto-generated by `scripts/build_index.py` — **do not hand-edit**
- Regenerate on every ticket add/move/frontmatter change
- Deterministic: running it twice produces zero diff
- CI fails if the committed INDEX.md is stale

---

## 12. Linter enforcement (`scripts/build_index.py`)

Fails the commit on any of:

- Unknown epic prefix (not in registry)
- Duplicate ID anywhere in `tickets/` or `hotfix/`
- `status:` frontmatter doesn't match folder name
- Missing required frontmatter fields
- Broken `blocks` / `blocked_by` / `parent` / `children` / `discovered_from` reference
- Epic code matches a synonym alias
- Filename doesn't match the `<ID>-<slug>.md` convention (section 2)
- Filename `<ID>` portion doesn't match the `id:` field in frontmatter
- `next_action:` missing or empty on a ticket in `active/` (section 5)
- `parked_until:` missing or empty on a ticket in `parked/` (section 5)
- INDEX.md not regenerated

Wired via pre-commit hook (local) + GitHub Action (CI).

---

## 13. Ticket file structure (one file per story)

A done ticket's file contains **both the plan and the retrospective** — one file per story, never split across plan-files and retro-files. Template sections:

1. `## Context` — why the ticket exists
2. `## Scope` — in/out
3. `## Plan` — steps to ship
4. `## Acceptance criteria` — binary measurable statements
5. `## Verification` — executable checks
6. `## Risks / open questions`
7. `## Decisions` — appended by `/decide` whenever an architectural choice is made
8. `## Retrospective` — filled after shipping; commit SHAs, deviations, lessons (moved to `tickets/done/` once this section exists)

When migrating legacy plan + retro pairs, merge them into a single ticket file with the above structure — never leave two files for the same story.

---

## 14. Rule-capture principle

If a decision establishes a durable rule (applies to future similar situations), it **must be captured in a file**, not just in a conversation or memory:

- Ticket/doc system rules → this file (`GOVERNANCE.md`)
- Coding standards → `guidelines/`
- AI-tool behavior rules → `.claude/CLAUDE.md` at project root (or your tool's equivalent)

Memory is fine as a personal reminder, but memory-only rules create drift (the author follows them, other agents don't see them). The test: "would another agent need to know this?" — if yes, it belongs in a file.

One-off decisions (specific to one ticket / one file / one moment) go in MIGRATION-LOG, ticket frontmatter, or commit messages — not this file.

---

## 15. Session hygiene (AI orchestration rules)

The meta repo is the **control plane** for AI-assisted work. Two rules keep sessions coherent across context resets:

### Rule 15.1 — Always pause at session end

Before ending any session with an active ticket, write the `next_action:` field. Skill: `/ticket-pause`.

**Why:** context dies when the AI session ends. The next session (fresh AI, no memory of your chat) re-hydrates from `next_action:` + ticket body + branch state. Without `next_action:`, resuming means re-reading everything and guessing where you stopped.

**How to apply:** at end of session, or before switching to another ticket, run `/ticket-pause`. One sentence in `next_action:`, concrete and imperative.

### Rule 15.2 — Capture decisions in the ticket, not in chat

Whenever the AI presents 2–3 options and you pick one, the decision (options considered + pick + rationale) must land in the current ticket's **Decisions** section. Skill: `/decide`.

**Why:** architectural decisions made in chat die with the session. Future-you (or future-AI) re-litigates the same question weeks later, often picking differently. The ticket is the durable record.

**How to apply:** when you pick between options the AI offered, the AI must offer to `/decide` before proceeding. Skip only for trivial picks (variable names, formatting). Anything that would change the shape of the solution → `/decide`.

---

## 16. Cross-references (where else things live)

- **Compliance:** `compliance/` — checklists, evidence (optional; populate if the project has compliance requirements). Not tickets.
- **Architecture:** `architecture/` — living design docs (not tickets; updated as architecture evolves).
- **Guidelines:** `guidelines/` — standards you must follow (best-practices, security, design).
- **Guides:** `guides/` — how-to walkthroughs.
- **Audits:** `audits/` — periodic-review procedures.
- **Migration history:** `MIGRATION-LOG.md` — permanent audit trail of file moves.
- **Strategic roadmap:** `ROADMAP.md` — narrative + `>>> CURRENT <<<` marker.
- **Operational snapshot:** `STATUS.md` — where we are now.

---

*This file is the law. If this file conflicts with another doc, this file wins — open a PR to update the other doc.*
