---
id: EPIC-N                       # required — immutable once assigned; see GOVERNANCE.md section 2
title: Short descriptive title   # required
epic: EPIC                       # required — must match Epic Registry in GOVERNANCE.md section 3
status: backlog                  # required — backlog | active | blocked | parked | done; must match folder
created: YYYY-MM-DD              # required — ISO date, set once
updated: YYYY-MM-DD              # bump on significant edits
parent: null                     # optional — another ticket ID (e.g. AUTH-1)
children: []                     # optional — list of ticket IDs
blocks: []                       # optional — list of ticket IDs this ticket blocks
blocked_by: []                   # optional — list of ticket IDs blocking this ticket
discovered_from: null            # optional — ticket ID that caused this ticket to be created
branch: null                     # optional — e.g. feat/EPIC-N-slug
repos: []                        # optional — sub-repos this ticket touches; see GOVERNANCE §5
next_action: null                # required when status == active; one-sentence next step; see GOVERNANCE §5 + §15
parked_until: null               # required when status == parked; names the activation trigger; see GOVERNANCE §5
---

## Context

Why does this ticket exist? What problem does it solve? Link to any preceding tickets, incidents, or external drivers.

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
