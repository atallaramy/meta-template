# AUTH — Authentication & session management

> Identity, login/logout, sessions, passwords, MFA, SSO, token lifecycle.

## Scope

### Owns
- Login and logout flows (UI + API)
- Password policy, password reset, email verification triggers
- Session management (cookies, tokens — whatever the project uses)
- Token issuance, refresh, revocation
- Brute-force lockout
- MFA (when implemented)
- SSO (when implemented)
- Auth-specific middleware (session, token parsing)

### Does NOT own
- Permission / RBAC rules → **SEC**
- Audit log writes for auth events → **OBS** owns the logging pipeline; AUTH emits structured events into it
- Delivery of password-reset / verification emails → email-transport epic if you have one; AUTH owns the trigger + template choice
- User-profile data unrelated to identity → relevant feature epic

### Interfaces with
- **OBS** — AUTH emits `login_success`, `login_failed`, `password_reset`, `account_lockout`, etc., as structured log events
- **SEC** — password policy + lockout parameters are defined here but audited by SEC

## Active work

*(See INDEX.md for the live view.)*

## Done work (summary)

*(none yet)*

## Backlog (priority order)

*(none yet)*

## Open design questions

- MFA: TOTP-only or include WebAuthn/passkeys from day one?
- SSO: which providers first?
- Session idle timeout: balance security vs. UX.

## External dependencies

- Auth library / framework choice (track CVEs).
