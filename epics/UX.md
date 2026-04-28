# UX — User experience foundations

> Design system, accessibility, internationalization, e2e UX testing.

## Scope

### Owns
- Design-system components and theming
- Accessibility standards (WCAG / ARIA)
- Internationalization framework + RTL support
- Loading / empty / error UX patterns
- E2E test framework (Playwright / Cypress / etc.) and conventions
- Front-end architectural patterns (state management, routing conventions)

### Does NOT own
- Per-feature screens → that feature's epic owns the screen, but consumes UX's design system
- Backend logic that powers a screen → backend feature's epic
- Per-feature copy / content → either the feature epic or **DOCS** if it's user-facing documentation

### Interfaces with
- **All feature epics** — they consume the design system; UX provides the contracts
- **DOCS** — UX provides component docs; DOCS provides the user-facing manual

## Active work

*(See INDEX.md for the live view.)*

## Done work (summary)

*(none yet)*

## Backlog (priority order)

*(none yet)*

## Open design questions

- Design-system source: build vs. adopt (Radix, shadcn, etc.)?
- i18n: which locales first?

## External dependencies

- Design tooling (Figma / etc.), translation pipeline.
