# The Core Loop — Foundational Practice

> **This is rule #0.** Every other rule in this folder, every memory entry, every coding guideline is downstream of this loop. **No compromises. No skipping. No "I'll do it next commit."**

## The loop

For **every** unit of work — feature, fix, refactor, doc, even a one-line change — iterate this loop until it converges:

1. **Write / stage.** Implement the change. Stage with `git add` (specific paths, never blanket `-A`).
2. **Review code.** Spawn the code-reviewer agent (project's chosen reviewer — e.g. `pr-review-toolkit:code-reviewer`) against the staged diff. Reviews: style, logic, project conventions (per this folder + `meta/guidelines/security-guidelines.md`), naming, dead code, abstraction fit.
3. **Review security.** Spawn the silent-failure / security reviewer agent against the staged diff AND do a manual security pass referencing `meta/guidelines/security-guidelines.md`. Covers: auth, crypto, sessions, cookies, input validation, error-response uniformity, OWASP Top 10.
4. **Cross-check community.** Spawn `best-practices` or `researcher` agent. Verify the approach against current external truth: OWASP / RFC / framework docs / recent CVEs / community-proven patterns. Stale knowledge is a defect — re-check every loop, especially for security code.
5. **Compare against current code.** Grep the codebase for the existing pattern that solves the same problem. If one exists and we're diverging, justify in a `/decide` entry — otherwise match it. Consistency wins over cleverness.
6. **Fix everything surfaced.** Every finding from 2 / 3 / 4 / 5 gets addressed *in this iteration*. No "I'll fix in next commit." No "minor, ignore." If a finding is genuinely wrong, push back in the conversation — do not silently dismiss.
7. **Loop.** Return to step 2 until **all** reviewers + community check + codebase cross-check come back clean in the same pass. A loop iteration that surfaces zero new findings is the exit condition.

Then — and only then — commit.

## Why this is rule #0

- **Reviewers catch what linters miss.** Linters check syntax. The code-reviewer catches logic. The silent-failure-hunter catches the silent `catch {}` and the missing `await`. The community check catches the security pattern that was best-practice 18 months ago and is a CVE today.
- **Stale knowledge is a defect class of its own.** Auth, crypto, cookie, and session patterns drift faster than ticket cycle time. Re-checking community sources every loop is how you don't ship a pattern that was right last quarter and wrong today.
- **Compounding.** A miss caught at step 2 is one rewrite. A miss caught in CI is a force-push. A miss caught in staging is a hotfix branch + incident. A miss caught in production is a compliance finding. Cost per stage scales ~10×.
- **Solo-dev / small-team means no second pair of eyes.** No human reviewer is going to bail you out. The agent reviewers ARE the second pair.

## What this loop is NOT

- **Not optional.** Not for "small" changes. Not for "obvious" fixes. Not for "just a typo." The discipline matters precisely because the small changes are where assumptions hide.
- **Not the pre-commit hook alone.** Pre-commit is the final checkpoint; this loop runs *during* implementation. By the time you're at pre-commit, the work should already have been reviewed multiple times.
- **Not "let the agent decide if it's worth running."** Always run. Always all four checks. The agent does not get to skip.
- **Not "I read the rules so I don't need the review."** The reviewers see the diff fresh. We see what we *intended*. Those are different things.

## Cross-references

- `.claude/CLAUDE.md` — Git Branch Workflow § "The Core Loop is rule #0" — the commit-time enforcement of step 7's exit condition.
- `meta/guidelines/security-guidelines.md` — what step 3 (security review) is checking against.
- `meta/guidelines/best-practices/overview.md` — the cross-stack baseline.
- Topic files in this folder — what step 2 (code review) is checking against for project-specific patterns.
