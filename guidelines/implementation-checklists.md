# Implementation Checklists

> Pre-flight checks for complex features. Add a checklist when a class of work is recurring and easy to get wrong.

## How to use

- Before starting an active ticket in a category covered below, run through the relevant checklist.
- If the ticket type is new and not yet listed, draft a checklist as part of the ticket's retrospective and add it here.

---

## New API endpoint

- [ ] Auth check — who can call this, and is that enforced at the framework level (not just in code)?
- [ ] Tenant / scope check — does the data filter by the right tenant / org / user?
- [ ] Validation — every input validated; no SQL/NoSQL injection vectors
- [ ] Error responses — consistent shape, no internal details leaked
- [ ] Audit log entry on mutating endpoints
- [ ] Rate-limiting — appropriate class for this endpoint
- [ ] OpenAPI / schema entry updated
- [ ] Tests: happy path + each failure mode + auth refusal

## New external integration

- [ ] Vendor risk assessment (security, availability, compliance impact)
- [ ] Secret stored in the managed secret store
- [ ] Timeout + retry policy chosen (fail-fast or fail-slow — be explicit)
- [ ] Circuit breaker if availability matters
- [ ] Telemetry — every call logged with correlation ID, latency, outcome
- [ ] Cost ceiling / budget alarm if usage is metered
- [ ] Vendor inventory updated

## New data model / migration

- [ ] Backwards-compatible? If not, what's the cutover plan?
- [ ] Online migration tested at scale
- [ ] Rollback plan documented
- [ ] PII / sensitive fields encrypted at rest
- [ ] Retention policy set
- [ ] Indexes for known query patterns

## New background job

- [ ] Idempotent — can it re-run safely?
- [ ] Failure mode — what happens on partial failure?
- [ ] Observability — start, success, failure events
- [ ] Concurrency — is single-runner enforced if it must be?
- [ ] Backpressure — what if the queue fills?

---

*Add project-specific checklists below this line.*
