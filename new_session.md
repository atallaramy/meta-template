# SESSION PROMPT — fixed shape, size-capped (GOVERNANCE §20)

> **A SNAPSHOT, not a log.** OVERWRITE `Where we got to` · `This session` · `State` every session;
> `Boot` · `First message` · `Which ticket` are STANDING. **Never append.** Enforced by
> `meta/scripts/build_index.py --validate`: **140 lines / 12 KB**, and `Where we got to` is capped
> at **3 entries**. Detail is NOT duplicated here — a trap's durable home is its own ticket
> (`## Context` / `## Plan` step 0); what happened goes to the shipping ticket's
> `## Retrospective`; where we are goes to `meta/STATUS.md`.
> *(Symlink this file to your project root: `ln -s meta/new_session.md new_session`.)*

## Boot

**A brand-new terminal every session — nothing is running.** Start what you need yourself, and
never suggest "move to a new session" as a way to defer work.

Scan what you need — direct reads, no skipping: `meta/STATUS.md`, `meta/ROADMAP.md`
(`>>> CURRENT <<<`), `meta/GOVERNANCE.md`, `meta/INDEX.md`, your AI-tool config
(e.g. `.claude/CLAUDE.md`), `meta/guidelines/` (`core-loop.md` first — rule #0).

## First message

Before any work and before any scan report — short plain prose, in this order:

1. **THE OWNER'S NEXT STEPS** — a short numbered list of only what THEY do (a decision to make ·
   a thing to verify · when to merge). One line each.
2. **ANY PENDING HAND-OFF** — or one line saying there is none. Do not invent one.
3. **WHERE WE GOT TO** — the `Where we got to` entries below, in clear short prose.

THEN GO on `This session` — do not wait.

## Which ticket

When `This session` names no ticket: **one ordered source, no browsing.** Stop at the first hit.

1. **Any open `P0`** — `cd meta && python3 scripts/build_index.py --priority P0`. A P0 interrupts.
2. **The first unstarted item in `meta/ROADMAP.md` § Execution queue.** In order.
3. **Nothing eligible → STOP AND ASK.** Offer exactly three candidates, one line each. Do not
   choose, and do not go shopping in `backlog/` — the backlog is a record, not a queue
   (GOVERNANCE §19.8).

## Where we got to

*(max 3 sessions — overwrite, never append; older detail lives in the tickets)*

- *(nothing yet — first session fills this in)*

## This session

*(Overwrite each session: the ticket — or the auto-pick above — the domain reads, the branch.)*

## State

*(Overwrite each session: SHAs, suite results, counts, merge authorisation. Never add a dated
block below — replace this one.)*

**At session end:** `/ticket-pause` (or ship), update STATUS + `next_action:`, then **OVERWRITE**
the three snapshot sections of this file. Standing sections stay verbatim. If the commit is
refused for the cap, you appended — trim, don't raise the cap (GOVERNANCE §20).
