# ADR-002: Internationalization Strategy — react-i18next, English-first

- **Status**: Accepted
- **Date**: 2026-05-06

## Context

Satlas targets a global audience — researchers, defense professionals, and students across different countries. As an open-source project, it should be accessible to contributors and users who are not native English speakers. The creator is Korean, which makes Korean a natural first addition beyond English.

Localization decisions are costly to change later. Hardcoded UI strings require touching every component when i18n is retrofitted.

## Decision

Adopt **react-i18next** for frontend internationalization from day one.

- **Primary language**: English (`en`) — all UI strings defined here first
- **First additional language**: Korean (`ko`) — added by the project creator
- **Further languages**: Added by contributors as the project grows (Chinese, Russian, etc.)

All UI text is stored in `src/locales/{lang}.json`. Hardcoding UI strings in components is not allowed.

Language preference is stored in `localStorage`. No URL-based routing per language (e.g., `/en/`, `/ko/`) — a language toggle in the UI is sufficient at this scale.

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| English only, no i18n library | Simpler setup | Costly to retrofit later; excludes non-English users |
| English only with i18n structure | Low upfront cost, future-proof | Slight overhead with no immediate payoff |
| Full i18n from day one (en + ko) | Complete from start | More upfront work; ko strings may lag behind en |

## Consequences

- `src/locales/en.json` is the source of truth for all UI strings
- `src/locales/ko.json` ships with the project from the start
- Contributors can add new language files without touching component code
- CONTRIBUTING.md should document how to add or update translations
