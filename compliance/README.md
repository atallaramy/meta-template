# Compliance

> Living checklists and evidence for whatever compliance regimes the project must meet (SOC2, HIPAA, ISO 27001, GDPR, etc.). Optional folder — delete if your project has no compliance requirements.

## Structure

- `<framework>-checklist.md` — control-by-control checklist with status (met / partial / gap)
- `<framework>-evidence/` — pointers to where evidence lives (logs, screenshots, runbooks, audit reports)
- `encryption-documentation.md` — encryption posture summary if required by the framework

## How to use

- Update the checklist at the end of each ticket that touches a compliance-relevant control.
- Evidence is audit-ready — auditors should be able to follow links from the checklist to working artifacts.
- New compliance requirements that emerge from a ticket get filed back into the relevant framework checklist.

## What does NOT belong here

- Tickets — `compliance/` is reference material, not work-tracking. Compliance gaps surfaced during work become **SEC** or **<owning-epic>** tickets.
- Generic security guidelines — those live in `guidelines/security-guidelines.md`.
