# OBS — Observability

> Logging, metrics, tracing, error reporting, alerts, dashboards.

## Scope

### Owns
- Structured logging pipeline (collection, shipping, retention)
- Metrics + dashboards
- Distributed tracing
- Error reporting (Sentry / Rollbar / etc.)
- Alerts and on-call routing
- Log retention policy

### Does NOT own
- Audit-log policy / what-must-be-logged for compliance → **SEC** sets the policy; OBS provides the pipeline
- Per-feature instrumentation (which spans, which counters) → that feature's epic decides; OBS provides the SDK + conventions
- Provisioning the underlying compute → **INFRA**

### Interfaces with
- **INFRA** — observability backends live in cloud resources INFRA provisions
- **SEC** — SEC says "auth events must be retained 1 year"; OBS implements the pipeline that achieves it
- **All feature epics** — they emit events; OBS owns the conventions

## Active work

*(See INDEX.md for the live view.)*

## Done work (summary)

*(none yet)*

## Backlog (priority order)

*(none yet)*

## Open design questions

- Self-hosted vs. SaaS for telemetry?
- Cost ceiling for log retention?

## External dependencies

- Telemetry vendor SLAs.
