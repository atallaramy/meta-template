# API — API contract & versioning

> API versioning strategy, contract testing, schema management, error-code immutability.

## Scope

### Owns
- API versioning strategy (v1 → v2 transitions)
- OpenAPI / GraphQL schema management
- Contract testing between services
- Error-code registry + immutability rules
- API deprecation policy
- Cross-service request/response conventions (auth headers, tracing, etc.)

### Does NOT own
- Individual API endpoints → that feature's epic owns the endpoint; API owns the conventions it must follow
- API documentation as user-facing reference → **DOCS** for public docs; API owns the schema source-of-truth
- Authentication of API requests → **AUTH**

### Interfaces with
- **All feature epics** — they implement endpoints conforming to API's contracts
- **DOCS** — DOCS publishes the public reference; API ensures the reference comes from a single source-of-truth

## Active work

*(See INDEX.md for the live view.)*

## Done work (summary)

*(none yet)*

## Backlog (priority order)

*(none yet)*

## Open design questions

- REST vs. GraphQL vs. RPC?
- Versioning style: URL path, header, query param?
- Public vs. internal API split?

## External dependencies

- Schema-registry service (if used).
