# claude-config — optional Claude Code integration

> **Optional folder.** Delete it if you don't use Claude Code. Everything else in `meta/` works without it.

This folder contains backup copies of the AI tooling that lives at your project root in `.claude/`:

- `agents/*.md` — generic specialized agents (committer, planner, analyzer, structure, researcher, best-practices)
- `commands/*.md` — slash commands that automate the ticket lifecycle (`/ticket-start`, `/ticket-resume`, `/ticket-pause`, `/ticket-ship`, `/decide`)
- `CLAUDE.md` — project-level Claude Code instructions slice

## Why backup copies live here

Claude Code reads `.claude/` at the project root. Those files are not in any sibling repo (the project root is typically not a git repo). This folder is the version-controlled backup so your AI tooling survives a fresh Claude Code install or accidental deletion.

## Setup on a new project

After running `bootstrap.sh`:

```sh
# From the project root (parent of meta/)
mkdir -p .claude/agents .claude/commands
cp meta/claude-config/agents/*.md .claude/agents/
cp meta/claude-config/commands/*.md .claude/commands/
cp meta/claude-config/CLAUDE.md .claude/CLAUDE.md
```

## Keep in sync

When you edit a live file at `.claude/<...>`, also update the matching file here (or the other way). Quick diff:

```sh
diff -r .claude/agents/ meta/claude-config/agents/
diff -r .claude/commands/ meta/claude-config/commands/
diff .claude/CLAUDE.md meta/claude-config/CLAUDE.md
```

## What's NOT included

This folder ships only **stack-agnostic** agents (committer, planner, analyzer, structure, researcher, best-practices). Add stack-specific agents (linters, testers, debuggers for your specific tech) to `.claude/agents/` and copy them here when you want them version-controlled.
