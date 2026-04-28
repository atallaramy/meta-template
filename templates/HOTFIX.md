---
id: HF-YYYY-MM-DD-slug
title: Short descriptive title
epic: EPIC                       # the epic this hotfix belongs to (even though it's filed under hotfix/)
status: active                   # active | done
created: YYYY-MM-DD
updated: YYYY-MM-DD
parent_ticket: null              # the ticket most closely related, if any
discovered_from: null            # ticket or event that revealed the issue
branch: hotfix/HF-YYYY-MM-DD-slug
severity: high                   # critical | high | medium
---

## Incident

What broke? When was it detected? How was it detected? Who/what is affected?

## Root cause

Technical explanation. Prefer evidence (logs, SQL, stack traces) over speculation.

## Fix

What change ships in this hotfix. Keep minimal — anything non-essential belongs in a follow-up ticket.

## Verification

How we confirmed the fix works.

- [ ] Check 1
- [ ] Check 2

## Follow-ups

Links to tickets spawned by this hotfix (deeper fixes, prevention, monitoring). Set `discovered_from: HF-YYYY-MM-DD-slug` on each.

## Timeline

- `YYYY-MM-DD HH:MM UTC` — detected
- `YYYY-MM-DD HH:MM UTC` — root cause identified
- `YYYY-MM-DD HH:MM UTC` — fix merged
- `YYYY-MM-DD HH:MM UTC` — verified in production
