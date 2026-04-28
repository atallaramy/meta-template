# CICD — Continuous integration & deployment

> Build pipelines, test runners, deploy automation.

## Scope

### Owns
- CI workflows (GitHub Actions / GitLab CI / etc.)
- Build pipelines (image builds, artifact publishing)
- Test runner setup and reporting
- Deploy automation to all environments
- Branch protection + merge rules
- Release tagging strategy
- Rollback automation

### Does NOT own
- The application code being deployed → that feature's epic
- The infrastructure being deployed *to* → **INFRA**
- Code-quality tooling rules (linters, formatters) → defined in `guidelines/`; CICD just runs them

### Interfaces with
- **INFRA** — CICD calls infra deploy commands (Terraform apply, kubectl, etc.)
- **SEC** — SEC defines rules CICD enforces (signed commits, secret scanning, dependency checks)
- **DX** — agents and meta-tooling sometimes touch CI; CICD owns the pipeline, DX owns what runs in it for dev experience

## Active work

*(See INDEX.md for the live view.)*

## Done work (summary)

*(none yet)*

## Backlog (priority order)

*(none yet)*

## Open design questions

- Trunk-based vs. develop/main split?

## External dependencies

- CI provider, container registry, secret store.
