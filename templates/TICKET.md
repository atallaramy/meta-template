---
id: EPIC-N                       # required — immutable once assigned; see GOVERNANCE.md section 2. EPIC-N is a PLACEHOLDER: the validator rejects it until you substitute a registry code + number.
title: Short descriptive title   # required
epic: EPIC                       # required — must match Epic Registry in GOVERNANCE.md section 3
status: backlog                  # required — backlog | active | blocked | parked | done; must match folder
priority: P3                     # required on backlog/active — P0|P1|P2|P3. Spawned (discovered_from set) → born P3; root (customer/roadmap/plan) → P2. See GOVERNANCE §9.3 + §19.
priority_because: null           # required for P0/P1 (a §19.4 trigger, as fact) AND for a spawned backlog P2 (one line — who is hurt, and when). Validator-enforced.
proposed_priority: null          # optional — a session's promotion/queue proposal awaiting the owner's word; silence = not yet; listed by build_index.py --health. See GOVERNANCE §9.2.
created: YYYY-MM-DD              # required — ISO date, set once
updated: YYYY-MM-DD              # bump on significant edits
parent: null                     # optional — another ticket ID (e.g. EX-1)
children: []                     # optional — list of ticket IDs
blocks: []                       # optional — list of ticket IDs this ticket blocks
blocked_by: []                   # optional — list of ticket IDs blocking this ticket
discovered_from: null            # optional — ticket ID that caused this ticket to be created
branch: null                     # optional — e.g. feat/EPIC-N-slug
repos: []                        # optional — sub-repos this ticket touches; see GOVERNANCE §5
sensitive: false                 # true if this touches regulated/sensitive data; gates ## Compliance Impact rigor; see GOVERNANCE §17
next_action: null                # required when status == active; one-sentence next step; see GOVERNANCE §5 + §15
parked_until: null               # required when status == parked; names the activation trigger; see GOVERNANCE §5
---

## Context

Why does this ticket exist? What problem does it solve? Link to any preceding tickets, incidents, or external drivers.

## Compliance Impact

Required — silence is not clearance. Set `sensitive:` in frontmatter (true if this touches, stores, transmits, or logs regulated/sensitive data). Name the controls this touches, advances, or depends on, cross-referencing your `compliance/` checklist by item. If genuinely compliance-neutral (refactor, CI, docs), write "none" + a one-line justification. Projects with no compliance regime write "none — no regime adopted" once and move on.

## Scope

### In scope
- Concrete items this ticket delivers.

### Out of scope
- Items explicitly not handled here (link to the ticket that does if known).

## Plan

Numbered or checkbox list of steps. Each step should be small enough to ship as one commit (or one logical commit group).

- [ ] Step 1
- [ ] Step 2

## Acceptance criteria

Binary, verifiable statements. If you can't measure it, rephrase it.

- [ ] Criterion 1
- [ ] Criterion 2

## Verification

How will this be verified? Commands, test names, URLs, metric thresholds. Prefer executable checks over human inspection.

## Risks / open questions

- Risk or open question.

## Decisions

*(Appended by `/decide` whenever an architectural choice is made. Each entry: options considered, pick, rationale, date. See GOVERNANCE §15.2.)*

<!-- Example:
### YYYY-MM-DD — Short title of the decision
- **Options:** (a) option one, (b) option two, (c) option three
- **Pick:** (a) option one
- **Why:** one or two sentences — the actual reasoning
-->

## Retrospective

*(Filled after the work ships. Moved to `tickets/done/` once this section exists and acceptance criteria are all checked.)*

### What actually shipped
- Commit SHAs + PR links.

### Deviations from plan
- What changed during execution and why.

### Lessons / follow-ups
- Any tickets spawned by this work (set `discovered_from` on them).
