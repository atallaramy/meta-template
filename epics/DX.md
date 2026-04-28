# DX — Developer experience

> Meta-repo tooling, AI agent definitions, slash commands, project-specific best-practices, governance evolution.

## Scope

### Owns
- Meta-repo tooling (`scripts/`, `templates/`, governance evolution, MIGRATION-LOG process)
- AI agent definitions (`.claude/agents/*` or equivalent for your tooling)
- Slash commands / skills
- Project-specific best-practices folder (`guidelines/`)
- Local-dev tooling not owned by another epic
- Onboarding documentation for new contributors

### Does NOT own
- Feature code → each feature's epic
- CI/CD pipelines themselves → **CICD**
- Domain-specific guidelines already owned by another epic (e.g. `security-guidelines.md` → **SEC**; `design-system.md` → **UX**)

### Interfaces with
- **All epics** — DX provides the tooling and conventions; epics use them

## Active work

*(See INDEX.md for the live view.)*

## Done work (summary)

*(none yet)*

## Backlog (priority order)

*(none yet)*

## Open design questions

- Which AI tooling stack? (Claude Code, Aider, Cursor — choose one and standardize.)

## External dependencies

- AI tooling licenses / quotas.
