# ADR-008: Repository Structure — Monorepo

- **Status**: Accepted
- **Date**: 2026-05-06

## Context

Before setting up the project directory, the repository structure must be decided: a single monorepo containing both frontend and backend, or separate repositories for each.

This decision affects CI/CD pipeline design, contributor onboarding friction, and how cross-cutting changes (API + frontend together) are managed.

## Decision

**Use a monorepo with the following top-level structure:**

```
satlas/
├── backend/
│   ├── app/
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   └── package.json
├── docs/
├── docker-compose.yml
└── README.md
```

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| **Monorepo (chosen)** | Single PR for cross-cutting changes, full context visible to contributors, less overhead for a solo maintainer | CI requires path-based triggers to avoid running all tests on unrelated changes |
| Separate repos | Clear separation, independent release cycles | Cross-cutting changes require two PRs, harder to keep API contracts in sync, painful to merge later if needed |

## Consequences

- A single clone gives contributors the full picture — API shape and frontend usage in one place
- Cross-cutting changes (e.g., new endpoint + corresponding UI) ship in a single PR
- GitHub Actions uses path-based triggers: frontend changes run frontend CI, backend changes run backend CI
- Splitting into separate repos later is straightforward if team structure warrants it; the reverse is not
