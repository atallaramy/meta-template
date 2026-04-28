# Security Guidelines

> Coding rules for security-sensitive code. Audited by **SEC**, implemented across all epics.

## General

- Verify with OWASP, RFCs, and the project's threat model before writing security code.
- Never log secrets, tokens, passwords, or PII. Scrub before emitting to telemetry.
- Never put real secrets, passwords, or API keys in code, comments, or docs. Reference the source instead.
- Never disable a security check (e.g. `--no-verify`, signing skips) unless the user explicitly authorizes it.

## Authentication

- Sessions: short access lifetimes, longer refresh, rotation on every refresh.
- Lockout after N failed attempts. Log the events (don't expose them to the client).
- Password reset tokens: single-use, short TTL, bound to email + user-id.

## Cookies

- `Secure`, `HttpOnly`, `SameSite=Lax` (or `Strict` if cross-site is not needed) by default.
- Domain scope: tightest that works for the app.

## Cryptography

- Use the platform's standard library / vetted package — never roll your own.
- Authenticated encryption only (AES-GCM, ChaCha20-Poly1305).
- Random: cryptographic RNG (`secrets` in Python, `crypto.randomBytes` in Node).

## Audit logging

- Log auth events, permission changes, admin actions, data exports.
- Audit logs are immutable. Append-only sink, separate retention.
- Include who, what, when, where (IP / device), correlation ID.

## Headers

- CSP, HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.
- Frame ancestors locked down unless the app needs to be embedded.

## Inputs

- Validate at every system boundary (user input, external APIs, queue messages).
- Use parameterized queries. Never concatenate SQL.
- Treat URLs from external sources as untrusted — validate scheme + host before fetching.

## Secrets

- Stored in a managed secret store, not in env files or code.
- Rotation cadence defined per secret class (see SEC tickets).
- Access logged + audited.

## Threat model

- Maintain a document covering: assets, threats, mitigations, residual risk.
- Update on major architecture changes.

---

*Add project-specific rules below this line as they emerge. See GOVERNANCE §14.*
