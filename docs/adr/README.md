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
| [ADR-007](ADR-007-api-design-style.md) | API Design Style — REST over GraphQL | Accepted |
| [ADR-008](ADR-008-monorepo-structure.md) | Repository Structure — Monorepo | Accepted |
| [ADR-009](ADR-009-orm-strategy.md) | Database Access Strategy — SQLAlchemy ORM + Alembic | Accepted |
| [ADR-010](ADR-010-testing-strategy.md) | Testing Strategy — Real Database, No Mocks | Accepted |
| [ADR-011](ADR-011-logging-strategy.md) | Logging Strategy — structlog, JSON in Production | Accepted |
| [ADR-012](ADR-012-frontend-map-library.md) | Frontend Map Library | Accepted |
| [ADR-013](ADR-013-satellite-categorization.md) | Satellite Categorization | Accepted |
| [ADR-014](ADR-014-deployment-platform.md) | Deployment Platform — Fly.io (Backend) + Vercel (Frontend) | Accepted |
| [ADR-015](ADR-015-tle-ingest-push-model.md) | TLE Ingestion via GitHub Actions Push Model | Accepted |
| [ADR-016](ADR-016-positions-precache.md) | Satellite Positions Pre-cache | Accepted |
| [ADR-017](ADR-017-satellite-metadata-pipeline.md) | Satellite Metadata Pipeline — CelesTrak GP JSON + SATCAT | Accepted |
| [ADR-018](ADR-018-overhead-membership-refresh.md) | Overhead Membership Refresh — Server-Window Prediction + Client-Side Gating | Accepted |
| [ADR-019](ADR-019-visit-frequency-sort.md) | Visit Frequency Sort — 24-hour Pass Count per Country | Accepted |
| [ADR-020](ADR-020-overhead-prewarm-and-vm-upgrade.md) | Overhead Prewarm + shared-cpu-2x VM Upgrade | Accepted |
| [ADR-021](ADR-021-celery-worker-for-prewarm.md) | Celery Worker for Overhead Prewarm | Accepted |
| [ADR-022](ADR-022-prewarm-sgp4-dedup.md) | Hoist SGP4 Propagation Out of Per-Country Prewarm | Accepted |
| [ADR-023](ADR-023-redis-self-host-sjc.md) | Self-Hosted Redis in sjc (replaces cross-Pacific Upstash) | Accepted |
| [ADR-024](ADR-024-chunked-visits-recompute.md) | Chunked visits/recompute + Redis list storage | Accepted |
| [ADR-025](ADR-025-ip-geo-i18n-and-dynamic-og.md) | IP-geo language pick + per-country OG image variants | Superseded |
| [ADR-026](ADR-026-qa-environment-strategy.md) | QA Environment Strategy — Vercel Preview First, Backend QA Deferred | Accepted |

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
