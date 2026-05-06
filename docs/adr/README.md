# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for Satlas.

An ADR documents a significant architectural decision: what was decided, why, and what alternatives were considered. ADRs are immutable once accepted — if a decision changes, a new ADR supersedes the old one rather than editing it.

---

## Index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-message-queue.md) | Message Queue — Celery + Redis instead of RabbitMQ | Accepted |
| [ADR-002](ADR-002-i18n-strategy.md) | Internationalization Strategy — react-i18next, English-first | Accepted |
| [ADR-003](ADR-003-disputed-territories.md) | Disputed Territory Policy — Natural Earth + Visual Distinction | Accepted |
| [ADR-004](ADR-004-system-architecture.md) | System Architecture — Dual-Mode Service + Load Assumptions | Accepted |
| [ADR-005](ADR-005-data-storage-strategy.md) | Data Storage Strategy — TLE Snapshots + Phased Pre-computation | Accepted |
| [ADR-006](ADR-006-authentication-strategy.md) | Authentication Strategy — OAuth2-First with Passkey Pre-design | Accepted |

---

## How to Read an ADR

Each ADR follows this structure:

- **Context**: What situation prompted the decision
- **Decision**: What was decided
- **Alternatives Considered**: Other options that were evaluated
- **Consequences**: What changes as a result

---

## How to Add a New ADR

1. Copy the naming pattern: `ADR-NNN-short-title.md`
2. Follow the existing structure
3. Set status to `Accepted` when the decision is final
4. Add an entry to the index above
5. Update the Notion decision log with the human-readable version
