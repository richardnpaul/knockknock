---
trigger: always_on
---

# Localisation (l10n) Rules

These rules govern localisation across all code, configuration, templates, and UI components in this repository.

## 1. Mandatory Localisation Skill Follow-Through
- Whenever working on features, UI components, notifications, user messages, documentation, or changes that touch user-facing content, you **MUST** follow the `localisation-l10n` skill (`.agents/skills/localisation-l10n/SKILL.md`).
- Adhere strictly to the principles, architectural patterns, and formatting guidelines defined in the `localisation-l10n` skill.

## 2. Zero Hardcoded Language Strings
- **NEVER** hardcode user-facing strings directly in production code, templates, HTML, or component logic.
- This includes, but is not limited to:
  - UI labels, button text, headings, body copy, and status badges.
  - Form placeholders, input hints, validation messages, and tooltips.
  - Error messages, alerts, dialogue prompts, confirmation modals, and toast notifications.
  - Accessibility labels (e.g., `aria-label`, `aria-description`, image `alt` attributes).
  - Context menu titles, command descriptions, extension popup/sidepanel text, and extension notifications.
- All user-facing strings **MUST** be extracted into the appropriate localisation catalog/files (e.g., WebExtension `_locales/<locale>/messages.json` or framework-specific translation resource files) using descriptive, hierarchical key names.

## 3. String Interpolation and Dynamic Text
- **NEVER** use string concatenation or template literals (`"Hello " + name` or `` `Showing ${count} items` ``) to construct localized sentences or messages. Word order, grammar, and inflection vary across languages.
- You **MUST** use parameterized message placeholders or ICU message format with named placeholders (e.g., `$COUNT$`, `{count}`, `{name}`) as supported by the localisation system.
- Handle pluralisation and gender variations through dedicated localisation mechanisms (such as ICU plural rules or `Intl.PluralRules`), never with hardcoded inline conditionals (e.g., `count === 1 ? 'item' : 'items'`).

## 4. Regional and Cultural Conventions
- **Dates, Times, Numbers, and Currencies**: **NEVER** format dates, times, numbers, percentages, or currencies using manual string manipulation, hardcoded separators, or fixed formats. You **MUST** use the standard `Intl` API (`Intl.DateTimeFormat`, `Intl.NumberFormat`, `Intl.RelativeTimeFormat`, `Intl.PluralRules`) respecting the user's active locale.
- **Layout Adaptability**:
  - Always design UI containers to accommodate 30–50% text expansion (e.g., German translations vs English). Avoid fixed-width containers that cause text clipping or overflow.
  - Use CSS logical properties (e.g., `margin-inline-start`, `padding-inline-end`, `text-align: start`, `inset-inline-start`) instead of physical directional properties (`margin-left`, `padding-right`, `left`) to ensure native Right-to-Left (RTL) support.

## 5. Verification and Testing
- When writing tests (in accordance with TDD rules), verify that:
  - Localised keys are referenced rather than hardcoded string literals.
  - Required translation keys exist in the default locale catalog (e.g., `en`/`en-GB`).
  - Formatting helpers and dynamic parameter substitutions render accurately with simulated locale data.
