# Slash Commands — ticket lifecycle

These commands automate the ticket lifecycle defined in `meta/GOVERNANCE.md`. They're stack-agnostic and ship with the meta template.

## Commands

| Command | Purpose | Rule source |
|---|---|---|
| `/ticket-start <ID>` | Move backlog → active, set status, create branches in listed sub-repos | GOVERNANCE §4 (folder=status), §7 (branch naming), §5 (`repos:` field) |
| `/ticket-pause [<ID>]` | Write `next_action:`, stamp STATUS, regen INDEX. No WIP commit. | GOVERNANCE §15.1 (always pause at session end), §5 (`next_action:` field) |
| `/ticket-resume <ID>` | Read `next_action:`, show branch state, prime context. Read-only. | GOVERNANCE §5 (`next_action:` as handoff pointer) |
| `/decide [<ID>]` | Append a decision (options + pick + rationale) to the active ticket | GOVERNANCE §15.2 (decisions live in tickets, not chat) |
| `/ticket-ship <ID>` | Fill retrospective, move active → done, append to FEATURES.md, regen INDEX | GOVERNANCE §4 (folder=status), §13 (plan + retro in one file) |

## Where they live

- **Live (read by Claude Code):** `<project-root>/.claude/commands/<name>.md`
- **Backup (version-controlled):** `meta/claude-config/commands/<name>.md`

## Restore from backup

```sh
mkdir -p .claude/commands
cp meta/claude-config/commands/*.md .claude/commands/
```

## Keep in sync

When you edit a live file, update its backup here. Quick diff:

```sh
diff -r .claude/commands/ meta/claude-config/commands/
```

## Why automate this?

The commands enforce GOVERNANCE rules that are easy to forget under time pressure (writing `next_action:` before ending a session, capturing decisions, validating before merging). The skill files are **regeneratable** — the rules in GOVERNANCE.md are the source of truth. If you lose the skills, the rules survive.
