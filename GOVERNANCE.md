# Ticket System Governance

**Owner:** this repo is the single source of truth for ticket system rules. No other file defines these rules.
**Applies to:** every ticket, epic, hotfix, architecture doc, and migration action in this repo.
**Worked examples** in this file use the fictional epic `EX` (e.g. `EX-1`) — or the metasyntactic
`EPIC-N` where any code would do — and letter-form hotfix dates (`HF-YYYY-MM-DD-…`), so no real
project's IDs leak into the template. Substitute your own.

---

## 1. Ticket types

| Type | What it is | Folder | Filename pattern |
|---|---|---|---|
| **Epic** | Domain-level capability charter (not a task — a scope definition) | `epics/` | `<CODE>.md` |
| **Story** | A concrete, shippable unit of work inside an epic | `tickets/{status}/` | `<CODE>-<N>-<slug>.md` |
| **Sub-task** | Optional split of a large story | `tickets/{status}/` | `<CODE>-<N>-<slug>.md` (flat ID, same shape as a story; relationship encoded via `parent:` / `children:` frontmatter — NOT in the ID) |
| **Hotfix** | Urgent, out-of-band fix. Date-stamped, not epic-numbered. | `hotfix/` | `HF-YYYY-MM-DD-<slug>.md` |

---

## 2. ID scheme

- Format: `<EPIC>-<N>` (story OR sub-task) or `HF-YYYY-MM-DD-<slug>` (hotfix)
- `<EPIC>` is a code from the **Epic Registry** (section 3).
- `<N>` is the next available integer within that epic, **never recycled**.
- **Sub-tasks use flat IDs**, not decimals. A sub-task's relationship to its parent is encoded in the `parent:` / `children:` frontmatter fields — never embedded in the ID. Example: when `EPIC-7` is split into sub-tasks, the children are `EPIC-8`, `EPIC-9` (next available `<N>` in the same epic), each with `parent: EPIC-7`, and `EPIC-7` carries `children: [EPIC-8, EPIC-9]`. Reasoning: a decimal ID like `EPIC-7.1` reads like a version label, not a child reference; flat IDs match Jira / Linear / GitHub Issues conventions.
- **`<EPIC>-<N>.<M>` (decimal) form is deprecated for new tickets** but the validator regex retains it so any historical decimal IDs you carry forward stay valid. Do not introduce new `.M` IDs.
- **IDs are immutable once assigned.** Filename slug can be renamed, folder can change (status transitions), but the `ID` field in frontmatter is permanent.
- **Retroactive numbering is chronological.** When assigning IDs to existing-but-unticketed work, number by the order the work actually shipped (earliest = N=1), not by file creation date. This keeps the ticket timeline aligned with the git history.
- **Regex:** `^([A-Z]{2,8}-\d+(\.\d+)?|HF-\d{4}-\d{2}-\d{2}-[a-z0-9-]+)$` (accepts both flat and historical `.M` forms; do not use `.M` for new tickets)

### Filename convention

- **Tickets:** `<ID>-<slug>.md` — e.g. `EX-1-login-flow.md`
- **Hotfixes:** `<ID>.md` — e.g. `HF-YYYY-MM-DD-broken-deploy.md` (ID already contains the slug)
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

Add when you need them: `DATA` (data model, migrations, ETL), `BILLING`, `EMAIL`, `TENANCY` (multi-tenancy), `COMPL` (compliance work), `PERF` (performance). Adding a new code requires the add-epic gate (section 10). (To pre-approve a code without seeding its charter yet, put it under an optional `### Reserved` heading — the validator treats backticked reserved codes as valid; suggestions in THIS section are deliberately not.)

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

**Priority rides the transition** (§19): moving a ticket INTO `parked/` (or `done/`) removes its `priority:` line — nothing is waiting on it; moving it back to `backlog/` assigns one in the same edit. The validator enforces both directions.

---

## 5. Frontmatter schema

The full schema (the validator hard-requires `id`, `title`, `epic`, `status`, `created`, plus the conditional fields each subsection names; the rest are optional-but-recommended):

```yaml
---
id: EX-1                             # immutable once assigned
title: Login flow
epic: EX                             # must match epic registry (EX is this file's example epic)
status: active                       # backlog | active | blocked | parked | done
priority: P1                         # P0|P1|P2|P3; required on backlog/active; see §19
priority_because: Blocks the current gate — step 3 cannot run.  # required when P0|P1; one factual line
proposed_priority: null              # optional — a promotion proposal awaiting the owner's word; see §9.2
created: 2026-01-15                  # ISO date, set once
updated: 2026-01-15                  # bumped on significant edits
parent: null                         # or another ticket ID
children: []                         # list of ticket IDs
blocks: []                           # list of ticket IDs this ticket blocks
blocked_by: []                       # list of ticket IDs blocking this ticket
discovered_from: null                # ticket ID that caused this ticket to be created
branch: feat/EX-1-login-flow         # or null
repos: []                            # sub-repos this ticket touches; validated against VALID_REPOS when configured (required once SIBLING_REPOS is set — §15.1)
sensitive: false                     # true if this touches regulated/sensitive data; gates ## Compliance Impact; see §17
next_action: Run smoke tests.        # one sentence; required when status == active
parked_until: null                   # required when status == parked; names the external trigger
---
```

List fields use **bracket form** (`blocked_by: [EX-1, EX-2]`, `[]` when empty). The multi-line
`- item` YAML form is rejected repo-wide — the frontmatter parser is deliberately minimal and would
silently read it as empty.

### `priority:` / `priority_because:` — when do we do this

- **Purpose:** answer *when*, not *how bad*. Defined against the current milestone gate named in `ROADMAP.md`, never against a product phase — see §19.
- **Required** when `status` is `backlog` or `active` (validator enforces). `done/` and `parked/` carry none.
- **Values:** `P0` (stop now) · `P1` (do next — blocks the gate) · `P2` (before launch, not before the gate) · `P3` (later — **the default for spawned tickets**).
- **`priority_because:`** — one factual line naming which of §19.4's five triggers applies. **Required and validator-enforced when priority is P0 or P1**, and for a spawned backlog P2 (§9.3). If it can't be written in one line, it isn't P0/P1.
- **Assigned at filing time** (§9.3); the owner confirms every P0/P1.

### `proposed_priority:` — a promotion proposal awaiting the owner

- A session that believes a ticket earns a promotion or a queue slot sets this field (the argued fact goes in `priority_because`) and asks the owner in one line. **Silence means NOT YET, never "gone"** — `build_index.py --health` lists every unanswered proposal. See §9.2.

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
  - A descriptor pointing at another condition (e.g. `after-EX-7-ships`, `first-enterprise-customer`)
- **Single trigger per ticket:** if multiple triggers could activate the ticket, pick the **earliest realistic** one. Document the canonical trigger names somewhere stable in your project (a `READINESS.md` doc, or this file) so naming stays consistent — tickets reference these names; one source of truth keeps drift out.
- **Why parked, not blocked:** `blocked` is for internal dependencies (another ticket); `parked` is for external events. See §4 "blocked vs parked" semantic distinction.

### `repos:` — which sub-repos the ticket touches

- **Values:** any repo names you use. Configure the allow-list in `scripts/build_index.py` (`VALID_REPOS`); empty = free-form — **until you arm the §15.1 ship gate** (`SIBLING_REPOS`), at which point the validator REQUIRES the allow-list: without it, a `repos:` typo silently hides a ticket from the gate.
- **Used by** `/ticket-start` to know where to create the feature branch. A ticket with `repos: [backend, frontend]` gets a branch in both.

### `sensitive:` — the per-ticket compliance flag

- **Purpose:** mark whether the ticket touches regulated or sensitive data (PII, health data, financial records — whatever your compliance regime covers) or a compliance control. Bool, default `false`.
- **When `true`:** the `## Compliance Impact` section (§13) is **required** and validator-enforced (§17). When `false`, the section still exists but writes "none" + a one-line justification.
- **Validator:** rejects malformed values (must be literal `true`|`false`). See §17. Projects with no compliance regime leave every ticket at `false` — the gate then costs nothing.

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
| Story | `feat/<EPIC>-<N>-<slug>` e.g. `feat/EX-1-login-flow` |
| Sub-task of a story | `feat/<EPIC>-<N>-<slug>` (same shape as a story — sub-task uses its own flat ID; parent/child relationship lives in frontmatter, not in the branch name) |
| Hotfix | `hotfix/HF-<date>-<slug>` |
| Refactor with no feature change | `chore/<EPIC>-<N>-<slug>` |

### One branch carries an INCREMENT, which may be several tickets

The patterns above name a branch carrying ONE ticket — the default, right for a standalone unit of
work. They are not a rule that every ticket gets its own branch. **When two or more tickets will
merge together, they share ONE branch named for the increment** (e.g. `feat/signup-and-validation`),
not for whichever ticket happened to start first. Every participating ticket sets `branch:` to that
same value; the field records where the work lives and is not required to be unique.

**Decide this when the FIRST of those tickets starts, not at merge time.** Earned in a source
project: two tickets that were one increment by the roadmap's own sequencing each took a
ticket-named branch, so the second had to be branched off the first and the PR was raised from a
branch whose name described only half of what it shipped.

---

## 8. Commit / PR rules

- Commit subject: `type(scope): description (TICKET-ID)` — ticket ID at end. Example: `feat(auth): add password strength meter (EX-3)`
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
         ├── YES → sub-task of current ticket (new flat ID `EPIC-<next-N>`; set `parent:` on the sub-task + add the new ID to the parent's `children:`)
         └── NO  → new story (`EPIC-<next-N>`) — set `discovered_from` to current ticket
                    ├── blocks current ticket? move current to blocked/, add blocked_by
                    └── doesn't block? current continues; new story enters backlog/
```

### 9.1 Implement-now vs own-session

After a new ticket is filed via the tree above, **always make an explicit pick** on execution
timing — bundle into the current PR, or defer to its own session — before continuing. Name both
options in chat with one-line rationale each; recommend one; ask the user if not already steered.

| Bundle now if … | Defer to own session if … |
|---|---|
| Related to current ticket's scope and small | Orthogonal scope or needs separate thinking |
| Skipping it leaves the trunk red after merge | Current PR is already pending merge or reviewed |
| The current PR can absorb it without ballooning | Bundling would require test skips / TODOs that compound |

Capture the pick in `/decide` in the parent ticket if it's non-trivial (e.g. cross-repo
coordination, architecture). Otherwise note in PR body. Without an explicit pick at the moment of
injection, the default behavior drifts — half the work bundles, half defers, and both invariants
(trunk = always-working, one-branch-per-feature) end up violated alternately.

### 9.2 Only PROMISES are SLOTTED in the ROADMAP queue

`ROADMAP.md` §Execution queue is the promise list — **capped at 7 live items, readable in one
screen** (`QUEUE_CAP` in `scripts/build_index.py`). What enters it: **P0s and P1s** (trigger-backed,
owner-confirmed) and **P2s the owner said yes to**. Adding an item names the item it displaces; a
shipped entry moves to `QUEUE-LOG.md` the same day. **A numbered item is one PROMISE, and a
deliberate batch (one branch, one review round) may carry more than one ticket** — the cap bounds
promises, not ticket IDs. Accepted in writing when the cap was set: the mechanical check counts
numbered lines, so bundling can technically dodge the displacement question; counting IDs instead
would forbid legitimate batches, and the owner reading a 7-line list is the real control.
Everything else — every P3, every unqueued P2 — is filed + indexed **only**: `INDEX.md` and
`build_index.py --priority` are its home, and that is enough. There is no "slot when convenient"
section.

**Proposing a slot costs the owner one word.** A session that believes a spawned ticket earns a
slot sets `proposed_priority:` in the ticket's frontmatter (the argued fact goes in
`priority_because`) and asks the owner in one line. **Silence means NOT YET, never "gone"** —
`build_index.py --health` lists every unanswered proposal, so a missed ask resurfaces mechanically.
The owner maintains nothing.

**The two failures this section absorbed in a source project, both measured:**
- *Why slotting existed:* six verified tickets were filed and **zero** reached the roadmap —
  invisible to scheduling, found by the owner, not by a check.
- *Why slot-everything died:* the fix overcorrected — with every filing required to appear in the
  queue document, the §Execution queue section grew to **~805 of the roadmap's 1049 lines** with 18
  "slot when convenient" clusters. A promise list that contains everything promises nothing, which
  is the first failure upside-down. The not-lost guarantee is the P3 stamp + `INDEX.md` +
  `--health`, not a line in the queue document.

### 9.3 Every new ticket is PRIORITISED at filing time

In the same commit that files a ticket, it carries a `priority:` (§19). **The default depends on
where the ticket came from:** a ticket spawned by other work (`discovered_from` set) is born
**P3** — recorded forever, promised to no one; a **root** ticket (customer, roadmap, business plan)
defaults **P2**. A spawned ticket earns P2 only with one factual line in `priority_because` naming
**who is hurt and when** — the validator refuses a spawned backlog P2 without one. P0 or P1
requires one of §19.4's five triggers written as fact into `priority_because:`, and the **owner
confirms it**; the validator rejects an empty justification. **A P0/P1 must also occupy a
`ROADMAP.md` Execution-queue slot in the same commit** — a promise is slotted by definition, and
the validator refuses an unslotted P0/P1 (§9.2).

**Filing something is not permission to work on it.** A finding surfaced by a review round enters
`backlog/` at P3 unless a fact says otherwise; **P0 interrupts, P1 becomes next, P2/P3 wait**
(§19.5). This is what stops a review round from setting the agenda — see §19.8 for the measurement
that made the rule necessary, and its sequel: with a universal P2 default the label stopped
discriminating entirely (in the source project, 164 of 166 open prioritized tickets carried the
same label), which is why the default split.

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
- `repos:` contains a value outside `VALID_REPOS` (section 5 — only when the allow-list is configured)
- `priority:` missing on a `backlog`/`active` ticket, or not one of `P0|P1|P2|P3` (§19)
- `priority:` present on a `done`/`parked` ticket (§19 — only work that WAITS carries one)
- `priority_because:` missing/empty on a P0/P1, or on a spawned backlog P2 (§19.4 + §9.3)
- `proposed_priority:` invalid, or present on a done ticket (§9.2)
- priority inversion — a ticket `blocked_by` a lower-priority blocker (§19.5)
- a P0/P1 absent from the ROADMAP Execution queue, or the queue over its cap / missing its markers (§9.2)
- `ROADMAP.md` not declaring exactly one `>>> CURRENT GATE <<<` block (§19.1)
- `created:` / `updated:` present but not a real ISO date (section 5 — an unsubstituted `YYYY-MM-DD` placeholder counts)
- `SIBLING_REPOS` configured without `VALID_REPOS`, or naming a repo outside it (tunables coherence — §15.1)
- `sensitive:` value is not a literal `true`|`false` (section 5)
- `validate_compliance_section` — a `sensitive: true` ticket missing `## Compliance Impact` (§17)
- `validate_done_unchecked_criteria` — a done ticket with unchecked acceptance criteria and no `PENDING-VERIFICATIONS.md` row (§15.3)
- `validate_shipped_but_active` — a ticket whose work merged but is still `active` (§15.1; reports itself unavailable where it cannot run)
- `validate_status_snapshot` — `STATUS.md` exceeds the snapshot size cap (§18)
- `validate_new_session_prompt` — `new_session.md` missing, breaking its fixed shape, listing more than 3 sessions, or exceeding its size cap (§20)
- INDEX.md not regenerated

Wired via pre-commit hook (local) + GitHub Action (CI).

---

## 13. Ticket file structure (one file per story)

A done ticket's file contains **both the plan and the retrospective** — one file per story, never split across plan-files and retro-files. Template sections:

1. `## Context` — why the ticket exists
2. `## Compliance Impact` — regulated-data surface + controls touched (cross-ref your `compliance/` checklist), or "none" + one-line justification. Required non-empty when `sensitive: true` (§17).
3. `## Scope` — in/out
4. `## Plan` — steps to ship
5. `## Acceptance criteria` — binary measurable statements
6. `## Verification` — executable checks
7. `## Risks / open questions`
8. `## Decisions` — appended by `/decide` whenever an architectural choice is made
9. `## Retrospective` — filled after shipping; commit SHAs, deviations, lessons (moved to `tickets/done/` once this section exists)

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

The meta repo is the **control plane** for AI-assisted work. These rules keep sessions coherent across context resets:

### Rule 15.1 — Merged work SHIPS. Only unfinished work pauses.

**Ask first: did this ticket's code merge?**

- **Merged → `/ticket-ship`.** Not at session end — **at the merge**, in the same session, as part of the post-merge lifecycle. A ticket whose code is on trunk is finished work; leaving it `active` makes `active/` describe nothing.
- **Not merged → `/ticket-pause`.** Write `next_action:` and stamp `STATUS.md` before ending the session.

**Why the ship half had to be written down** (measured in a source project): 32 tickets sat in `active/`, **every one with its code already merged**. Three mechanical causes, none of them indiscipline:

1. **The rule only contemplated a ticket still in flight.** It said "always pause at session end," so pausing a finished ticket *satisfied the rule*. The record went stale while the process reported success.
2. **The cheap door was mandatory and the expensive door optional.** `/ticket-pause` costs a sentence; `/ticket-ship` costs a conversation. At session end, guess which one gets picked. Keep `/ticket-ship` a single owner turn for exactly this reason.
3. **Nothing connected "merged" to "ship."** The review loop ended at *"THEN commit"* and the committer's job ended at branch cleanup.

**Why pause still matters:** context dies when the AI session ends. The next session (fresh AI, no memory of your chat) re-hydrates from `next_action:` + ticket body + branch state. Without `next_action:`, resuming means re-reading everything and guessing where you stopped.

**How to apply:** merged → `/ticket-ship <ID>` at the merge. Unfinished → `/ticket-pause` at session end, one sentence in `next_action:`, concrete and imperative. Never pause a ticket whose work has landed.

**Enforcement:** `scripts/build_index.py --validate` fails when a ticket is `active` while its `branch:` is gone from the remote and commits naming it are on trunk — i.e. it merged and was never shipped. The gate needs the sibling code repos (configure `SIBLING_REPOS` at the top of the script), so it runs in the working tree and **reports itself unavailable** (never a silent pass) in meta-only CI or while unconfigured.

### Rule 15.2 — Capture decisions in the ticket, not in chat

Whenever the AI presents 2–3 options and you pick one, the decision (options considered + pick + rationale) must land in the current ticket's **Decisions** section. Skill: `/decide`.

**Why:** architectural decisions made in chat die with the session. Future-you (or future-AI) re-litigates the same question weeks later, often picking differently. The ticket is the durable record.

**How to apply:** when you pick between options the AI offered, the AI must offer to `/decide` before proceeding. Skip only for trivial picks (variable names, formatting). Anything that would change the shape of the solution → `/decide`.

### Rule 15.3 — Unchecked acceptance criteria at ship-time must migrate to a tracked surface

A ticket may only move `active/` → `done/` when every checkbox in `## Acceptance criteria` is either:

1. **`[x]`** — verified at ship-time (the normal case).
2. **`[ ]`** with a `*(Pending: …)*` annotation AND a matching row in `PENDING-VERIFICATIONS.md`. The row names the ticket ID, the AC summary, the date/event trigger that closes it, and the operator verification command.

Done tickets are invisible to session-start scans (`/ticket-resume` / §15.1 only re-hydrates from `active/`). A `[ ]` left in a done ticket without a ledger entry is technical debt that future sessions cannot see — exactly the failure mode this rule eliminates.

**Why:** time-deferred acceptance criteria (next-nightly verifications, N-day retention windows, long-term volume observations) are real and legitimate, but they need a tracked surface so the operator gets pinged when the trigger fires. That surface is `PENDING-VERIFICATIONS.md` — a dedicated, **uncapped** ledger (unlike the size-capped `STATUS.md` snapshot; the ledger only grows, so it must not share the snapshot budget — §18). It is linked from `STATUS.md` (read at every session start), validator-enforced, and its entries compound across sessions; the done-ticket annotation cross-references back to the canonical AC text.

**How to apply:** at `/ticket-ship`, for each unchecked AC in the shipping ticket:

- If the AC can be verified NOW → tick it (ideally with an inline `*(Verified <date>: <evidence>)*` note).
- If the AC is time-deferred → leave `[ ]`, append `*(Pending: <trigger> — verify via <command>)*` to the AC line, AND add a row to `PENDING-VERIFICATIONS.md` with the same trigger + command.
- If neither applies → ship is blocked; either drop the AC (with a `/decide` rationale) or hold the ticket.

When the trigger fires + verification passes, the operator (or the next-session AI on resume): (a) ticks the AC on the done ticket, (b) removes the row from `PENDING-VERIFICATIONS.md`. Same commit.

#### 15.3.1 — A deferral lives in an AC, NEVER in a code comment

**The rule:** anything switched off, stubbed, feature-flagged off, or deferred *"pending X"* must be an **unticked AC + a `PENDING-VERIFICATIONS.md` row**, naming X as the trigger. Writing it as a code comment, a `TODO`, or a sentence in the PR body does not count.

**Why (earned in a source project):** a branch was switched OFF *"pending X."* X shipped. Nobody switched it back on. It read as **done in the ticket, in the commit, and in the review** — and was only found a session later during an unrelated ship pass. In the shipping session's own words: *"a branch disabled 'pending X' is invisible once X lands, and it reads as done in the ticket, the commit and the review."*

No priority level can catch this (§19.6) — the ticket is already closed, so nothing is waiting and nothing is queued. The AC is the only surface the validator can see, and the rule above already refuses a done ticket with an unticked AC and no ledger row. Moving the deferral into an AC costs one line and makes the existing machinery do the work.

**How to apply:** at the moment you disable the branch — not at ship time — add `- [ ] <what turns back on> *(Pending: <X> — verify via <command>)*` to the ticket and the matching ledger row. If X is another ticket, also set `blocked_by`.

**Enforcement:** the validator (`scripts/build_index.py`) rejects any done ticket with unchecked acceptance criteria that lacks a matching row in `PENDING-VERIFICATIONS.md`. Pre-commit surfaces the violation; CI fails on push.

---

## 16. Cross-references (where else things live)

- **Compliance:** `compliance/` — checklists, evidence (optional; populate if the project has compliance requirements). Not tickets.
- **Architecture:** `architecture/` — living design docs (not tickets; updated as architecture evolves).
- **Guidelines:** `guidelines/` — standards you must follow (best-practices, security, design).
- **Guides:** `guides/` — how-to walkthroughs.
- **Audits:** `audits/` — periodic-review procedures.
- **Shipped-features log:** `FEATURES.md` — one row per shipped ticket, appended by `/ticket-ship`.
- **Production-readiness checklist (optional):** `PROD-READINESS.md` — if you keep one, the validator auto-ticks its checkboxes from ticket status (see `autotick_prod_readiness` in `scripts/build_index.py`).
- **Migration history:** `MIGRATION-LOG.md` — permanent audit trail of file moves.
- **Strategic roadmap:** `ROADMAP.md` — narrative + `>>> CURRENT <<<` marker + the `>>> CURRENT GATE <<<` block (§19.1) + the Execution queue (§9.2).
- **Queue history:** `QUEUE-LOG.md` — shipped queue entries move here the same day, verbatim, newest first (§9.2). Uncapped.
- **Operational snapshot:** `STATUS.md` — where we are now (fixed-shape, size-capped snapshot — see §18).
- **Deferred-AC ledger:** `PENDING-VERIFICATIONS.md` — the §15.3 tracked surface for time-deferred acceptance criteria from done tickets (uncapped; linked from STATUS; validator-enforced). See §15.3 + §18.
- **Session prompt:** `new_session.md` — the fixed-shape, size-capped prompt that starts a session, symlinked to the project root as `new_session` (which is how you open it). See §20.

---

## 17. Per-ticket compliance gate

Every ticket carries a `sensitive:` frontmatter field (bool, default false) and a `## Compliance
Impact` section. The section names the regulated-data surface + the controls touched,
cross-referencing your compliance checklist (in `compliance/`) by item. Compliance-neutral work
writes "none" + a one-line justification — silence is not clearance. A project with no compliance
regime keeps the field at `false` everywhere; the gate then never fires.

Enforcement: `scripts/build_index.py --validate` flags any `sensitive: true` ticket missing the
section, and rejects malformed `sensitive:` values. Pre-commit surfaces it; CI fails on push — same
path as §15.3. No `## Pending Verifications` bypass exists for this gate (stricter than §15.3 by
design).

Cross-refs: §5 frontmatter schema (`sensitive` field), §13 ticket structure (Compliance Impact
section), §16 (`compliance/` ledger).

---

## 18. STATUS.md is a snapshot, not a history log (size-capped)

`STATUS.md` answers exactly one question: **where are we right now.** It is NOT a session diary, a changelog, or a retrospective archive.

**Shape (fixed):**

1. A self-describing contract banner at the top (states this rule + the cap).
2. **One** `## Current State` block — the latest state only.
3. `## Next` — the next pick + a pointer to `ROADMAP.md` / `INDEX.md` (don't duplicate the backlog here).
4. `## Pending Verifications` — a **one-line pointer** to `PENDING-VERIFICATIONS.md`. The actual §15.3 ledger (which legitimately grows) lives in that dedicated, uncapped file; it must not share the snapshot budget. The cap **excludes** this section (`validate_status_snapshot` strips it before measuring), so a stub — or a table wrongly pasted back — never counts.
5. Optional live-state sections (e.g. `## Known Issues`, `## Quick reference`, `## Open architectural discussions`) — live operational state only, never history.

**The rule:** each session **OVERWRITES** the `## Current State` block. **Never prepend a new dated block.** SHAs, traps, root causes, fix-shapes, lessons → the shipping ticket's `## Retrospective` (`tickets/done/<ID>.md`), which is the durable historical record (§13). If you want to write history, you're in the wrong file.

**The forcing function:** a hard size cap — **120 lines / 16 KB by default**, tunable via `STATUS_MAX_LINES`/`STATUS_MAX_BYTES` in `scripts/build_index.py` — enforced by `validate_status_snapshot()` (pre-commit `--fix` + CI `--validate`/`--check`). A session that appends instead of overwriting blows the cap and the commit is refused. The cap is the mechanism; the banner + this section are the reminder. Note the validator enforces the CAPS plus the Pending-Verifications stub, not the section list — the shape above is convention here, unlike §20's, which is asserted heading-by-heading. (In the source project the file had reached 440 lines / 120 KB across 22 stacked dated blocks before this rule.)

**If you hit the cap**, the ledger cannot be the cause — Pending Verifications is excluded from the measurement. A cap hit unambiguously means the snapshot itself grew: you are appending history instead of overwriting the `## Current State` block. Fix that, don't raise the cap. Raise the constants only with a recorded reason. (Separately, if the *ledger* grows large, that's pressure to *close* stale verifications — but it never blocks a commit.)

Cross-refs: §12 (linter enforcement), §15.1 (`/ticket-pause` stamps STATUS), §15.3 (Pending Verifications → `PENDING-VERIFICATIONS.md`), §16 (the cross-reference map).

---

## 19. Priority levels (what a finding is ALLOWED to do)

Every ticket in `backlog/` or `active/` carries a `priority:`. It answers **when do we do this**, not how bad it is. `done/` and `parked/` carry none — done is done, and a parked ticket is waiting on a dated external trigger, not on us.

### 19.1 The gate pointer — why this survives the next product phase

The levels are defined against **the current milestone gate**, named in one line in `ROADMAP.md`. They never name a specific feature, customer, or product phase.

This is deliberate. A level defined as "blocks the launch demo" rots the day the demo ships. A pointer costs one line to move: demo → first real users → first paid pilot → next market. Same word, zero rewrites.

**There is exactly one current gate at a time, and it carries a date.** Changing it is an owner decision recorded in `ROADMAP.md`; everything labelled P1 re-points at the new gate automatically. The validator enforces exactly one `>>> CURRENT GATE <<<` block.

### 19.2 The four levels

| Level | Means | Test |
|---|---|---|
| **P0** | Stop now. | Data loss or corruption, security exposure, or a shipped artifact silently wrong. |
| **P1** | Do next. | Blocks the current gate — and you can name which step of it. |
| **P2** | Before launch, not before the gate. | Earned — one line names who is hurt and when. |
| **P3** | Later. | The default for spawned findings. Idea, debt, polish, latent guards. |

**P3 is the default for any ticket spawned by other work (`discovered_from` set); P2 must be earned
with one factual line in `priority_because` naming who is hurt and when.** A **root** ticket (no
`discovered_from` — it came from a customer, the roadmap, or the business plan) defaults P2. A
ticket does not earn P1 by being interesting, nearly finished, or freshly discovered — and it does
not earn P2 by being **true**; truth is the entry bar for filing, never a priority signal.
*(The split default is measured, not aesthetic: in the source project, eleven days after a
universal P2 default shipped, 164 of 166 open prioritized tickets were P2 and 0 were P3. A default
everything takes discriminates nothing.)*

### 19.3 The permanent floor (define per project)

Some defect class is never below P1 for you, whatever the current gate says — the class that breaks
the promise your product makes (a wrong shipped artifact, a privacy breach, a wrong financial
figure…). **Name YOURS here at project start.** Leave nothing here and this section reads "no
floor", which is also a decision.

### 19.4 What earns a P0 or P1 — the five triggers

One of these, stated as **fact**:

1. Data loss or corruption.
2. Regulated-data or security exposure.
3. A **reproducible** broken path on shipped code. Define *shipped* for your project (e.g. merged to trunk when staging is the only product surface).
4. **Blocks the named gate** — naming which step of it stops.
5. A dated **external** trigger, with the date written down (certificate renewal, audit window, upstream format change). Not a date we invented.

**Explicitly not evidence:** *"I want to work on it"*, *"it's interesting"*, *"it's nearly done"*, *"we're already in that file."*

**`priority_because:`** — one factual line naming the trigger. **Required and validator-enforced whenever `priority` is P0 or P1.** If the fact cannot be written in one line, it is not P0 or P1.

**Who assigns:** the agent proposes a level; the **owner confirms** every P0 and P1. The assigner is otherwise also the person who wants to do the work, and no rubric survives that. The required field does not make inflation impossible — it makes it visible, costly, and recorded.

### 19.5 Interrupt rights

- **P0 interrupts.** Stop what you are doing.
- **P1 becomes next.** It does not interrupt. Only the owner promotes a P1 to "now."
- **P2 / P3 wait**, and never auto-promote into `active/`.

"P0 and P1 may both interrupt" was considered and rejected: it reproduces the original defect in new clothing, because *"this is a P1"* becomes the universal justification for switching to whatever is more interesting than the gate.

A blocker also inherits its dependents' urgency: a P2 `blocked_by` a P3 is a promise the system has already decided never to keep — the validator rejects the inversion; raise the blocker or demote the dependent.

### 19.6 Priority is not the only mechanism — know which one you need

Priority governs work that **waits**. Three other cases are not priority problems at all, and using a level for them is the mistake:

| Situation | Mechanism |
|---|---|
| Defect **inside the diff you are building** | Fix it before you commit. Never becomes a ticket, so never needs a level. (Core Loop, `core-loop.md`) |
| Work deliberately switched off, stubbed, or deferred *"pending X"* | An **unticked AC + a `PENDING-VERIFICATIONS.md` row** (§15.3). **Never a code comment.** |
| Genuinely blocked on another ticket | `blocked_by:` + `blocked/` (§4, §9) |
| Waits in the backlog | `priority:` |

The middle row is the failure class §15.3.1 exists for: a branch switched off *"pending X"* stayed off after X shipped, and read as done in the ticket, the commit **and** the review. Priority could not have caught it — the ticket was already closed. An unticked AC would have, through §15.3's existing validator rule. A deferral that lives in a code comment lives where nothing can see it.

### 19.7 Enforcement

`scripts/build_index.py`:

- `--validate` — `priority` required on every `backlog`/`active` ticket; value must be one of `P0|P1|P2|P3`; `priority_because` non-empty whenever priority is P0 or P1, and on a spawned backlog P2. Pre-commit surfaces it, CI fails on push (§12).
- `--priority <level>` — deterministic query (`P0`, `P1`, …). "List all P0 tickets" is a **script**, never a judgement call.
- `--health` — the monthly gauge (§19.8): created vs closed, root vs spawned, priority histogram, unanswered proposals, and the self-feeding tripwire. Report-only.
- All the fields are emitted into `INDEX.json` and shown in `INDEX.md`.

`/ticket-start` refuses to promote a P2/P3 into `active/` while the `ROADMAP.md` execution queue has an unstarted item, unless the owner overrides — and the override is recorded with its one-line reason.

### 19.8 Why this section exists

Measured in a source project, from the filesystem: **every ticket created over an 11-day stretch —
60 of 60 — carried `discovered_from: <a prior ticket>`.** Zero root tickets — nothing entered the
system from a customer, from the roadmap, or from the business plan. Across all history, 253 of 301
tickets were review residue, and creation outpaced closure every month. This rule is that
measurement's fix.

That is the review loop **operating exactly as written**: "loop until a pass surfaces zero new
findings" + "fix everything, no deferrals" is a work generator with no throughput valve, because
the reviewers were pointed at the *system* rather than the *diff*. The review quality was never the
problem — those rounds find real reachable defects on shipped code. What a finding was **allowed to
do** was the problem.

The sequel lesson, same project: **a default everything takes discriminates nothing** — with a
universal P2 default, 99% of open tickets carried the same label, so the label answered no
question. Hence the §9.3 split default and the `--health` tripwire (ratio + floor) that watches for
the machine feeding itself.

**Capture is not commitment.** Every finding still gets written down. Only the execution queue is a
promise. A large backlog is a record, not a debt.

Cross-refs: §5 (frontmatter schema), §9 (injection — a priority is assigned at filing time), §9.2 (slotting in the ROADMAP queue), §12 (linter enforcement), §15.3 (deferred acceptance criteria), `ROADMAP.md` (the gate + the execution queue), `guidelines/best-practices/core-loop.md` (the in-diff / out-of-diff split).

---

## 20. `new_session` is a session prompt, not a session diary (size-capped)

`new_session.md` answers exactly one question: **how does a cold session start correctly.** It is NOT a diary, a changelog, or a place to park what a ticket already says.

**Where it lives:** tracked here, in the meta repo, with a symlink at the project root (`new_session → meta/new_session.md`) so the reader's path never changes. A fresh clone recreates the symlink with `ln -s meta/new_session.md new_session` from the project root — the tracked file is the artifact, the symlink is a convenience.

**Shape (fixed; items 2–7 asserted in order by the validator — item 1 is convention, not enforced):**

1. A contract banner naming which sections are standing and which are overwritten.
2. `## Boot` — what to scan; the "brand new terminal" fact. **Standing.**
3. `## First message` — the shape the owner wants their update in. **Standing.**
4. `## Which ticket` — the ordered auto-pick (§19). **Standing.**
5. `## Where we got to` — **at most 3 sessions.** Overwritten.
6. `## This session` — the ticket (or the auto-pick), the domain reads, the branch. Overwritten.
7. `## State` — SHAs, suite results, counts, merge authorisation. Overwritten.

**The rule:** each session **OVERWRITES** sections 5–7 and leaves 2–4 verbatim. **Never append.** The durable homes are the ones that already exist — what happened → the shipping ticket's `## Retrospective` (§13); where we are → `STATUS.md` (§18); *why a thing is not built and what will bite you* → **that ticket's own `## Context` / `## Plan` step 0**; how to run a command → the code's own README or a memory entry.

**Why there is no "held work" file.** The obvious fix for a growing "deliberately not done" list is to move it into a new uncapped sibling file — and that is wrong, because it relocates growth instead of ending it. Measured in the source project before deleting exactly such a list: **37 of 37 lead tickets already carried their own trap**, usually in more detail than the summary did. The list was 100% duplication of content the session reads anyway when `/ticket-start` opens the ticket. **A summary of N tickets is not a surface, it is a second copy that drifts.** This is the §15.3/§18 pattern's limit: an uncapped sibling file is right only when the content has no other home (`PENDING-VERIFICATIONS.md` rows do); it is wrong when the content's home already exists.

**The forcing function:** `scripts/build_index.py` `validate_new_session_prompt()` (pre-commit `--fix` + `--validate`/`--check`), three checks in increasing specificity:

| check | cap | catches |
|---|---|---|
| shape | the 6 headings, **exactly once each**, in order, and no others | a session rewriting the prompt freehand — and a DUPLICATE section, which is the append mode itself |
| **diary** | **3 entries under `## Where we got to`** | **the actual failure mode — appending a session** |
| size | 140 lines / 12 KB | everything else, incl. prose smuggled into few giant lines |

The diary cap is not redundant with the size cap and was verified so: appending a 4th session adds 2 lines, passes both size caps, and is caught only by the entry count.

**It counts SESSIONS, not one bullet syntax — and it parses markdown, not text.** The first version matched `- ` at column 0 and was defeated twelve ways, every one measured in the source project on a 28-session diary that stayed under every size cap: `* `, `+ `, `-<TAB>`, one leading space, `1. `, `1) `, a table, a duplicate section, a fenced block hiding either the entries or the whole shape, and one banner line containing the literal `` `## Where we got to` `` (the slice was a substring search, so it measured the banner). So: fenced blocks are masked before parsing, section bounds come from a line-anchored heading scan, entries include ordered lists and table body rows, nesting is resolved against the open item's content column, and a `- - -` rule is not an entry. The bypasses and the legitimate files that must NOT be rejected are pinned in `scripts/test_build_index.py`.

**If you hit a cap**, you appended. Trim; do not raise it. Raising `NEW_SESSION_MAX_*` / `NEW_SESSION_RECENT_MAX_BULLETS` costs a code edit **and** an amendment here, deliberately — same as §18.

Cross-refs: §12 (linter enforcement), §13 (a trap's durable home is its ticket), §15.1 (`/ticket-pause` stamps STATUS), §18 (the same snapshot discipline for STATUS), §19 (the auto-pick the prompt encodes).

---

*This file is the law. If this file conflicts with another doc, this file wins — open a PR to update the other doc.*
