# ADR-004: System Architecture — Dual-Mode Service + Load Assumptions

- **Status**: Accepted
- **Date**: 2026-05-06

## Context

Two architectural questions were decided together, as they are interdependent:

1. How should Satlas be offered — as a data API, a web service, or both?
2. What load ceiling should the architecture be designed for?

## Decision

### Service Mode

Satlas operates in two modes:

| Mode | Auth | Purpose |
|---|---|---|
| Public API | None | Programmatic data access for researchers and developers |
| Web Service (UI) | JWT (when user features exist) | Interactive globe, bookmarks, saved preferences |

The two modes share the same backend. The API is open by default (rate-limited). The web service adds a user layer on top.

**Implication**: The database schema must include `users` and `bookmarks` tables from the start, even if the feature ships later. Retrofitting these tables after data accumulates is costly.

### Load Assumptions

| Phase | Monthly Visits | Peak Concurrent | Timeframe |
|---|---|---|---|
| Launch | 1K–10K | ~100 | 0–6 months |
| Growth | 10K–100K | ~1,000 | 6–18 months |
| Mature | 100K+ | ~1,200 | 18 months+ |

**Design ceiling**: Heavens-Above equivalent (~500–1,200 peak concurrent). Architecture must support this scale. Infrastructure is provisioned at launch scale and grows as traffic warrants.

Reference: Heavens-Above ~450–620K monthly visits; N2YO ~220–340K. Satlas targets a narrower audience (researchers, defense professionals) so conservative estimates apply.

### Scaling Principles

- API server: **stateless** from day one — horizontal scaling requires no code changes
- Connection pooling on PostgreSQL — handles concurrent load without exhausting connections
- Celery workers: horizontally scalable — add workers without changing code
- Redis: single instance at launch (Upstash free tier), upgrade path clear

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| API only | Simple, no UI complexity | Excludes non-technical users |
| UI only | Better UX | Limits research/programmatic use |
| **Dual mode (chosen)** | Serves both audiences | More upfront design needed |

## Consequences

- `users` and `bookmarks` tables must be in the initial schema even if unused at launch
- JWT auth infrastructure planned from the start, activated when bookmark feature ships
- All API endpoints designed to be stateless
- Rate limiting applied to Public API from launch (no pricing tier initially)
