# DOCS — Documentation

> User-facing docs, READMEs, runbooks, public API references.

## Scope

### Owns
- User-facing product docs
- Top-level README and getting-started guides
- Operational runbooks (oncall procedures, incident playbooks)
- Public API reference (the published artifact; **API** owns the schema source-of-truth)
- Changelog / release notes
- Onboarding docs for end-users

### Does NOT own
- Internal architecture docs → `architecture/` folder, owned by the relevant feature epic
- Per-ticket plans / retrospectives → ticket files
- Code comments → that file's owning epic

### Interfaces with
- **API** — API provides the schema; DOCS publishes the human-readable reference
- **UX** — UX builds the design system; DOCS uses it for any docs site
- **All feature epics** — they hand off user-facing copy to DOCS at ship time

## Active work

*(See INDEX.md for the live view.)*

## Done work (summary)

*(none yet)*

## Backlog (priority order)

*(none yet)*

## Open design questions

- Docs platform: separate site (Docusaurus / etc.), in-product, or README-only?

## External dependencies

- Docs hosting (if separate from app).
