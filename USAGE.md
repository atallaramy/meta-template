# How to use this repo

> Practical patterns for common workflows. For rules, see `GOVERNANCE.md`.

**Read order at session start:**
1. `STATUS.md` — where things are today
2. `ROADMAP.md` — find `>>> CURRENT <<<`
3. The current ticket (linked from ROADMAP)
4. `GOVERNANCE.md` if you need to reference a rule

---

## Session lifecycle

### Start of session

Just tell the AI: `"continue from where we left off"` or `"new session — read status"`. It will read `STATUS.md` → `ROADMAP.md` → the current ticket, then offer the next step.

If you want the AI to pick up a specific ticket: `"work on EX-3"` or `"continue EX-1 phase 2"`.

### End of session — the "save state" pattern

Run `/ticket-pause` (or ask the AI to do it). This:

1. Writes `next_action:` in the active ticket frontmatter (one sentence — concrete, imperative)
2. Bumps `updated:` to today
3. Overwrites the `## Current State` block in `STATUS.md` (a snapshot, never an appended log — GOVERNANCE §18)
4. Regenerates `INDEX.md` + `INDEX.json`

No WIP commit is made — pause is a bookmark, not a checkpoint. If switching machines, also `git stash` or commit manually.

### Continuing a session

Run `/ticket-resume <TICKET-ID>` (or `/ticket-resume` if there's only one active ticket). It reads the ticket, reports `next_action:`, and shows branch state per repo. Read-only — does not pull or checkout anything.

---

## Ticket workflows

### Start a new feature

1. Pick the epic (see `GOVERNANCE.md` Epic Registry). If unsure, ask the AI to propose based on what the feature touches.
2. Ask: `"start a new feature: <one-line intent>, in epic <EPIC>"`.
3. AI copies `templates/TICKET.md` → `tickets/backlog/<EPIC>-<N>-<slug>.md`, fills frontmatter, drafts Context + Scope + Plan.
4. You review, adjust, approve.
5. Run `/ticket-start <TICKET-ID>` to move it to `active/` and create branches in the listed `repos:`.

### New ticket from a discovery mid-work

If you hit something while working on ticket X that needs its own story:

- **Urgent + small + out-of-band** → hotfix (next section)
- **Needed to complete current ticket** → sub-task with its own flat ID (`<EPIC>-<next-N>`, `parent:` set — GOVERNANCE §2)
- **Separate concern, not urgent** → new story in `backlog/`, set `discovered_from: <current-ticket-id>` in its frontmatter — it is **born P3** (GOVERNANCE §9.3). If it blocks the current work, move the current ticket to `blocked/` with `blocked_by: [<new-ticket-id>]`.

Tell the AI: `"discovered a new issue while working on X — it's Y. Create a ticket."` It'll apply the decision tree (GOVERNANCE section 9).

### Architectural decisions during work

When the AI presents 2-3 options and you pick one, run `/decide` to capture the decision into the active ticket's `## Decisions` section. Includes options + pick + rationale.

### Finish a feature

Run `/ticket-ship <TICKET-ID>` **at the merge, in the same session** — merged work ships, it does not pause (GOVERNANCE §15.1). It:

1. Asks for retrospective inputs (commit SHAs/PRs, deviations, lessons)
2. Fills the `## Retrospective` section
3. Updates frontmatter (`status: done`, clears `next_action:`)
4. `git mv` to `tickets/done/`
5. Appends one row to `FEATURES.md`
6. Regenerates INDEX

You commit + push manually.

### Hotfix workflow

Production/staging is on fire:

1. Ask: `"hotfix: <problem>"`.
2. AI copies `templates/HOTFIX.md` → `hotfix/HF-YYYY-MM-DD-<slug>.md`, fills Incident + Root Cause sections.
3. Branch: `hotfix/HF-YYYY-MM-DD-<slug>` cut from `develop` (or `main`).
4. Ship the fix, update the hotfix file with the Fix section + commit SHAs.
5. Merge. If deeper follow-up needed, AI opens a new ticket with `discovered_from: HF-YYYY-MM-DD-<slug>`.

---

## How priorities and the queue work

Four levels, answering **when**, not *how bad* (GOVERNANCE §19):

- **P0** — stop now (data loss, security exposure, a shipped artifact silently wrong). Interrupts.
- **P1** — do next; blocks the current gate (the dated one-liner in `ROADMAP.md`) and you can name which step. Becomes next, never interrupts.
- **P2** — before launch, not before the gate. Root tickets (customer/roadmap/plan) default here.
- **P3** — later. **Every ticket spawned by other work (`discovered_from` set) is born P3** — recorded forever, promised to no one. It earns P2 only with one line naming who is hurt and when.

The `ROADMAP.md` **Execution queue** is the only promise list — capped at **7 live items**; adding
one names what it displaces, and shipped entries move to `QUEUE-LOG.md` the same day. **Filing a
P0/P1 slots it in the queue in the same commit** — the validator refuses an unslotted P0/P1 (§9.2). Everything
else lives in `INDEX.md` — a record, not a debt. Propose a promotion by setting
`proposed_priority:` on the ticket; the owner answers in one word, and
`python3 scripts/build_index.py --health` (run monthly) resurfaces every unanswered proposal plus a
tripwire that fires when ticket creation is feeding on itself.

---

## Archiving (never delete)

`rm` is banned (`GOVERNANCE.md` section 6). When a file is superseded, uncertain, or obsolete:

- Ask: `"archive <filename> with note: <reason>"`.
- AI `git mv`s to `_archive/` and appends a line to `MIGRATION-LOG.md`.

If you're tempted to `rm`: don't. Archive and let it sit — near-zero cost, full audit trail.

---

## Common commands

```bash
# Regenerate INDEX.md + INDEX.json after any ticket edit
python3 scripts/build_index.py

# Validate only (no file writes) — fails on schema violations
python3 scripts/build_index.py --validate

# Check that committed INDEX files match ticket state — CI uses this
python3 scripts/build_index.py --check

# Find all backlog SEC tickets (jq on INDEX.json)
jq '.[] | select(.epic == "SEC" and .status == "backlog")' INDEX.json

# List all P0 / P1 tickets (deterministic — never eyeball the backlog)
python3 scripts/build_index.py --priority P0

# The monthly health gauge: created vs closed, root vs spawned, unanswered proposals
python3 scripts/build_index.py --health

# Find everything blocked by EX-3
jq '.[] | select(.blocked_by | contains(["EX-3"]))' INDEX.json

# Find tickets touched in the last week
jq '.[] | select(.updated >= "2026-01-01")' INDEX.json
```

---

## Asking the AI to do things well

**Good prompts:**
- `"resume EX-1 — read the ticket and propose the next step"`
- `"start a new INFRA feature: geo-redundant backups"`
- `"this is a hotfix: password reset links are broken in staging"`
- `"update STATUS and close EX-4, move to done, commit"`
- `"archive PLAN-foo.md — content already absorbed into EX-3"`

**Weak prompts (AI will ask clarifying questions):**
- `"fix the thing"`
- `"new ticket"`
- `"what's next"` (works but vague; the AI will pick something)

**Rule the AI follows:** any answer you give that implies a durable rule ("from now on", "always", "never") gets captured in `GOVERNANCE.md` / `guidelines/` / `.claude/CLAUDE.md`, not just AI memory.

---

## When something feels wrong

- Validation fails? Run `python3 scripts/build_index.py --validate` — the error tells you which ticket + which field
- Can't find a plan that used to exist? Check `MIGRATION-LOG.md` for old path → new path mapping, or `_archive/`
- Stuck deciding an epic? Read the epic charter (`epics/<CODE>.md`) — if boundaries still unclear, file a boundary question PR on GOVERNANCE.md

---

## Philosophy (short)

- **One source of truth per concept.** Rules in GOVERNANCE, roadmap in ROADMAP, ticket list in INDEX.
- **Folder = status.** No `status: "done"` in frontmatter that disagrees with the folder.
- **Immutable IDs.** Rename the slug, move between folders, but the ID never changes.
- **Evidence beats assertion.** Commit SHAs in the Retrospective section, not "we shipped it" claims.
- **Archive rather than delete.** Audit trail > tidiness.
