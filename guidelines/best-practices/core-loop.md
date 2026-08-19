# The Core Loop — Foundational Practice

> **This is rule #0.** Every other rule in this folder, every memory entry, every coding guideline is downstream of this loop. **No compromises. No skipping. No "I'll do it next commit."**

## The loop

For **every** unit of work — feature, fix, refactor, doc, even a one-line change — iterate this loop until it converges:

1. **Write / stage.** Implement the change. Stage with `git add` (specific paths, never blanket `-A`).
2. **Review code.** Spawn the code-reviewer agent (project's chosen reviewer — e.g. `pr-review-toolkit:code-reviewer`) against the staged diff. Reviews: style, logic, project conventions (per this folder + `meta/guidelines/security-guidelines.md`), naming, dead code, abstraction fit.
3. **Review security.** Spawn the silent-failure / security reviewer agent against the staged diff AND do a manual security pass referencing `meta/guidelines/security-guidelines.md`. Covers: auth, crypto, sessions, cookies, input validation, error-response uniformity, OWASP Top 10.
4. **Compliance lens (if your project has a regime).** Assess against your `compliance/` checklist. If the diff touches regulated data, access control, audit logging, or retention, map to the specific control(s) and confirm met in-diff. If not, state "no compliance surface" explicitly — silence is not clearance.
5. **Cross-check community.** Spawn `best-practices` or `researcher` agent. Verify the approach against current external truth: OWASP / RFC / framework docs / recent CVEs / community-proven patterns. Stale knowledge is a defect — re-check every loop, especially for security code.
6. **Compare against current code.** Grep the codebase for the existing pattern that solves the same problem. If one exists and we're diverging, justify in a `/decide` entry — otherwise match it. Consistency wins over cleverness.
7. **Fix everything surfaced INSIDE THE DIFF.** Every in-diff finding from 2 / 3 / 4 / 5 / 6 gets addressed *in this iteration*. No "I'll fix in next commit." No "minor, ignore." If a finding is genuinely wrong, push back in the conversation — do not silently dismiss. **A finding OUTSIDE the diff is filed, not fixed** — see §Step 0i.
8. **Loop, at most twice.** Return to step 2 until a pass surfaces zero new **in-diff** findings, **or you have run two passes** — whichever comes first. There is always a third finding; the cap is what makes the loop terminate.

Then — and only then — commit.

## Step 0i — a finding is filed by BLAST RADIUS, and the reviewers are briefed on the DIFF

**The rule, in two halves:**

1. **In-diff → fix before commit. Out-of-diff → file it with a `priority` and move on.** An
   out-of-diff finding enters `backlog/` at **P3** — recorded, promised to no one (GOVERNANCE
   §9.3). It earns P2 only with one factual line naming who is hurt and when
   (validator-enforced); P0/P1 need §19.4's triggers as fact. **P0 interrupts. P1 becomes next.
   P2/P3 wait.** Only the owner promotes, and **a ticket may not queue its own children** — only
   the owner or a P0/P1 trigger puts work on the §9.2 promise list. Leftovers at ship time: small →
   finish before shipping (it is in scope by definition); big → its own ticket, born at whatever
   the triggers say — a remainder ticket is a smell of an over-scoped cut, and "the parent just
   shipped" earns nothing.
2. **Brief the reviewers on the diff, not the system — and fix the diff's boundary BEFORE you
   start.** The ticket names its files + acceptance criteria first. Most out-of-diff findings then
   never get *generated*, which is far cheaper than triaging them afterwards.

**Why (measured in a source project, from the filesystem):** every ticket created over an 11-day
stretch — 60 of 60 — carried `discovered_from: <a prior ticket>`. **Zero root tickets** — nothing
entered the system from a customer, from the roadmap, or from the business plan. All-time: 253 of
301. Creation outpaced closure every month. This rule is that measurement's fix.

That is **this loop working exactly as written.** "Fix everything, no deferrals" + "loop until
zero findings" + reviewers pointed at the whole system is a work generator with no throughput
valve. The finding quality was never in question — the same rounds found real, silent defects on
shipped code. What a finding was **allowed to do** was the defect.

**The remaining loophole, named so it stays visible:** nothing mechanical stops you widening a
ticket's named files until every attractive side quest counts as "in-diff." Fixing the boundary
before work starts makes that visible and deliberate rather than gradual. If the ticket genuinely
must grow, the owner widens it — in the ticket, not in your head.

**Capture is not commitment.** Every finding is still written down. Only `ROADMAP.md`'s execution
queue is a promise. A large backlog is a record, not a debt — don't work it out of guilt.

Cross-refs: GOVERNANCE §19 (the levels + the gate pointer), §9.3 (prioritise at filing time),
§19.6 (priority is not the only mechanism — in-diff, deferred-`pending X`, and blocked each have
their own).

## Why this is rule #0

- **Reviewers catch what linters miss.** Linters check syntax. The code-reviewer catches logic. The silent-failure-hunter catches the silent `catch {}` and the missing `await`. The community check catches the security pattern that was best-practice 18 months ago and is a CVE today.
- **Stale knowledge is a defect class of its own.** Auth, crypto, cookie, and session patterns drift faster than ticket cycle time. Re-checking community sources every loop is how you don't ship a pattern that was right last quarter and wrong today.
- **Compounding.** A miss caught at step 2 is one rewrite. A miss caught in CI is a force-push. A miss caught in staging is a hotfix branch + incident. A miss caught in production is a compliance finding. Cost per stage scales ~10×.
- **Solo-dev / small-team means no second pair of eyes.** No human reviewer is going to bail you out. The agent reviewers ARE the second pair.

## What this loop is NOT

- **Not optional.** Not for "small" changes. Not for "obvious" fixes. Not for "just a typo." The discipline matters precisely because the small changes are where assumptions hide.
- **Not the pre-commit hook alone.** Pre-commit is the final checkpoint; this loop runs *during* implementation. By the time you're at pre-commit, the work should already have been reviewed multiple times.
- **Not "let the agent decide if it's worth running."** Always run. Always every check (code, security, compliance, community, codebase). The agent does not get to skip.
- **Not "I read the rules so I don't need the review."** The reviewers see the diff fresh. We see what we *intended*. Those are different things.

## Cross-references

- `.claude/CLAUDE.md` — Git Branch Workflow § "The Core Loop is rule #0" — the commit-time enforcement of step 7's exit condition.
- `meta/guidelines/security-guidelines.md` — what step 3 (security review) is checking against.
- `meta/guidelines/best-practices/overview.md` — the cross-stack baseline.
- Topic files in this folder — what step 2 (code review) is checking against for project-specific patterns.
