# Best Practices

> Code-quality and process standards for this project. Reference from tickets, PRs, and code reviews.

## Research-first

- Verify online before writing security-critical code (OWASP, RFCs, community patterns).
- Prefer community-proven libraries over custom implementations for security primitives.
- Document the source when adopting a pattern (link in the ticket Decisions section).

## Implementation plans

- Plans live in ticket files under `## Plan`. Not in chat, not in commit messages.
- Plans are checkboxes — concrete, shippable steps. Each step is a logical commit group.
- A plan section that survives in `tickets/done/` IS the historical record.

## Commits

- Format: `type(scope): description (TICKET-ID)`. Body explains *why*.
- Reference the ticket ID in every commit. Lets `git log --grep` reconstruct ticket history.

## Code review

- Run a code review on the staged diff before every commit (linter + reviewer agent + security pass).
- Fix all surfaced issues before committing — no "I'll fix it next commit" deferrals.
- Linters catch style; reviewers catch logic; security passes catch holes. All three.

## Refactoring

- No refactor-later. Pick the future-proof path now.
- Three similar lines is better than a premature abstraction.
- Don't add features, abstractions, or error handling beyond what the task requires.

## Decision-making

- At architectural decision points: pause, present 2-3 options with tradeoffs, recommend one, ask.
- Capture the decision into the ticket via `/decide` — options + pick + rationale.
- Don't silently pick. Decisions made in chat die with the session.

## Testing

- Test the *behavior*, not the *implementation*.
- Don't mock the database in integration tests — past projects got burned by mocked tests passing while prod migrations failed.
- Run tests inside the same container the app runs in — never on the host.

---

*Add project-specific rules below this line as they emerge. See GOVERNANCE §14.*
