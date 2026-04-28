# Audits

> Periodic-review procedures. Each file is a runbook for an audit type you run on a cadence.

## Examples of what belongs here

- `dependencies-audit.md` — quarterly review of dependency licenses + CVEs
- `access-audit.md` — quarterly review of who has access to what
- `e2e-tests-audit.md` — annual review of e2e coverage gaps
- `cost-audit.md` — monthly cloud-cost review

## Format

Each audit file:

1. **Cadence** — how often
2. **Owner** — who runs it
3. **Procedure** — step-by-step checks
4. **Evidence template** — what to capture
5. **Thresholds** — what counts as a finding

Findings become tickets. The audit file itself stays — you re-run the procedure next cycle.

## What does NOT belong here

- One-off audits → ticket file
- Compliance checklists → `compliance/`
