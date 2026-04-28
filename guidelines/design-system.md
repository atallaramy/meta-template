# Design System

> UX standards: components, accessibility, internationalization, loading patterns. Owned by **UX**.

## Components

- Single source of truth for UI primitives (buttons, inputs, modals, etc.).
- Each component has: variants, accessibility annotations, light/dark theme tokens.
- No bespoke styling per screen — extend the system instead.

## Accessibility

- WCAG 2.1 AA minimum.
- Every interactive element keyboard-reachable, with visible focus.
- ARIA labels on icon-only buttons.
- Test with screen readers on critical flows.

## Internationalization

- All user-facing strings via the i18n layer — no hardcoded copy.
- Date / number / currency formatting via locale-aware helpers.
- RTL layouts work with the same components (no fork).

## Loading / empty / error states

- Every async UI has explicit loading, empty, and error states (not just success).
- Loading: skeleton, not spinner, when the layout is known.
- Errors: actionable message + retry, not "something went wrong."

## Forms

- Inline validation, with errors announced to assistive tech.
- Disable submit while pending; show progress.
- Server-side validation always — client-side is convenience only.

## Theming

- Tokens (color, spacing, typography), not hardcoded values.
- Per-tenant or per-brand theming routes through the same token layer.

---

*Add project-specific rules below this line as they emerge. See GOVERNANCE §14.*
