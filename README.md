# meta — project control plane

Single source of truth for plans, tickets, architecture docs, guidelines, audits, and compliance checklists.

> **You are reading the template.** This folder is project-agnostic. To use it on a real project: copy this folder to `<your-project>/meta/`, then run `./bootstrap.sh` from inside it. See [Bootstrapping a new project](#bootstrapping-a-new-project) below.

## What lives here vs. elsewhere

- **This repo (`meta`)** → all documentation, tickets, plans, compliance, architecture
- **Sibling repos** → application code (backend, frontend, infra, etc.)

Each sibling has its own git history and CI/CD. This repo is the human-and-AI-readable layer that ties them together.

## Read these first

1. **`GOVERNANCE.md`** — the rulebook. Ticket types, epic registry, archival rules, linter behavior. If any doc conflicts with GOVERNANCE, GOVERNANCE wins.
2. **`STATUS.md`** — where we are right now. Read at session start.
3. **`ROADMAP.md`** — where we're going. Current priorities + `>>> CURRENT <<<` marker.
4. **`INDEX.md`** — auto-generated list of every ticket. Source of truth for status/links.
5. **`USAGE.md`** — how to drive the system (start/continue/end session, new feature, hotfix, common commands, good prompts).

## Directory map

```
meta/
├── GOVERNANCE.md               # rulebook
├── STATUS.md                   # operational snapshot
├── ROADMAP.md                  # strategic direction
├── INDEX.md                    # auto-generated ticket index
├── MIGRATION-LOG.md            # permanent file-move audit trail
├── FEATURES.md                 # shipped-features log
│
├── epics/                      # one charter per epic (scope/owns/excludes)
├── tickets/
│   ├── active/                 # in-progress stories
│   ├── backlog/                # identified, not started
│   ├── blocked/                # blocked_by another ticket
│   └── done/                   # shipped stories (plan + retrospective)
├── hotfix/                     # urgent out-of-band fixes
│
├── architecture/               # living design docs
├── guides/                     # how-to walkthroughs
├── guidelines/                 # standards (coding, security, design)
├── audits/                     # audit procedures (periodic reviews)
├── compliance/                 # checklists + evidence (optional)
├── templates/                  # TICKET / EPIC / HOTFIX templates
│
├── scripts/                    # build_index.py (validator + INDEX generator)
├── claude-config/              # optional: Claude Code agents + slash commands
└── _archive/                   # superseded / uncertain-relevance files
```

## Workflow

- **New ticket:** copy `templates/TICKET.md` into `tickets/backlog/<EPIC>-<N>-<slug>.md`, fill frontmatter, set `epic:` from the registry.
- **New hotfix:** copy `templates/HOTFIX.md` into `hotfix/HF-YYYY-MM-DD-<slug>.md`.
- **Status change:** `git mv` the ticket file between `tickets/{active,backlog,blocked,parked,done}/` and update the `status:` frontmatter field (linter enforces they match). `parked/` is gated by an external trigger (see `GOVERNANCE.md` §4 + `parked_until:` in §5).
- **Regenerate INDEX.md:** `python scripts/build_index.py` (CI fails if it's stale).
- **Archive a file:** `git mv` to `_archive/` + add entry to `MIGRATION-LOG.md`.
- **Never `rm`:** see GOVERNANCE section 6.

## Linter

`scripts/build_index.py --validate` runs via pre-commit + GitHub Actions. Fails the commit on: unknown epic prefix, duplicate ID, `status:` ≠ folder, broken cross-references, missing frontmatter fields. See GOVERNANCE section 12.

## Bootstrapping a new project

This folder is a template. To use it in a new project:

```sh
# 1. Clone or copy meta-template/ into your project root, rename to meta/
cp -R meta-template/ /path/to/new-project/meta

# 2. Run the bootstrap script (substitutes project name, optionally inits git)
cd /path/to/new-project/meta
./bootstrap.sh

# 3. (Optional) Install pre-commit hooks
pre-commit install
```

After bootstrap, `bootstrap.sh` deletes itself. Edit `STATUS.md`, `ROADMAP.md`, and the seed epics to reflect your project.
