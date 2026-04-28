# SEC — Security hardening

> Cross-cutting security posture: CSP, headers, secrets, audit policy, RBAC, vulnerability response.

## Scope

### Owns
- Security headers (CSP, HSTS, frame-options, etc.)
- Secret management policy (rotation cadence, who-can-read)
- Audit-log policy — what events must be logged, retention, immutability requirements
- RBAC rules and authorization model
- CSRF / XSS / SQLi defenses (the policy; implementation lives in the affected code)
- Vulnerability response runbook
- Dependency scanning + advisory triage
- Pen-test findings remediation

### Does NOT own
- The auth system itself → **AUTH** (SEC audits AUTH's password policy; AUTH implements it)
- Compliance evidence (SOC2/HIPAA/etc.) → `compliance/` (out-of-tree from epics)
- Per-feature security work → that feature's epic implements; SEC reviews

### Interfaces with
- **AUTH** — AUTH implements; SEC audits and sets policy
- **OBS** — SEC defines what to log; OBS provides the pipeline
- **INFRA** — INFRA provisions secret stores; SEC owns the policy on what goes in them
- **CICD** — CICD enforces SEC rules at PR-time (signed commits, secret scanning)

## Active work

*(See INDEX.md for the live view.)*

## Done work (summary)

*(none yet)*

## Backlog (priority order)

*(none yet)*

## Open design questions

- Secret rotation cadence?
- Threat-model document — when?

## External dependencies

- Vulnerability scanners, advisory feeds.
