# ADR-009: Database Access Strategy — SQLAlchemy ORM + Alembic

- **Status**: Accepted
- **Date**: 2026-05-06

## Context

Before writing the first endpoint, the database access pattern must be decided. Two options were evaluated: raw SQL via asyncpg directly, or SQLAlchemy ORM with asyncpg as the underlying driver.

This decision affects how every contributor writes database queries and how schema migrations are managed.

## Decision

**Use SQLAlchemy 2.0 (async ORM) + asyncpg driver + Alembic for migrations.**

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| **SQLAlchemy ORM + Alembic (chosen)** | Industry standard, familiar to most Python contributors, connection pooling built-in, Alembic integration seamless | Learning curve for SQLAlchemy 2.0 async patterns |
| asyncpg (raw SQL) | Transparent SQL, lower abstraction | Custom connection management, Alembic setup is more manual, higher contributor onboarding cost |

## Why SQLAlchemy for an Open-Source Project

The primary driver is **contributor onboarding cost**. SQLAlchemy is the de facto standard for Python web backends — most contributors already know it. A custom asyncpg wrapper requires contributors to learn project-specific patterns before they can submit their first PR.

## Performance Consideration

At Satlas's design ceiling (~1,200 peak concurrent, Heavens-Above scale), ORM overhead is unmeasurable compared to the actual performance factors: index coverage, Redis caching (ADR-005), and client-side position computation (ADR-005).

The main ORM risk — N+1 queries from lazy loading — is eliminated in SQLAlchemy async mode: lazy relationship access raises an error at development time, forcing explicit eager loading (`selectinload`, `joinedload`).

## Consequences

- `sqlalchemy[asyncio]>=2.0` and `alembic>=1.13` added to dependencies
- `asyncpg` remains as the database driver (SQLAlchemy uses it internally)
- All schema migrations managed via Alembic (`backend/alembic/`)
- Async session factory injected via FastAPI dependency injection
- Contributors follow SQLAlchemy 2.0 async patterns — documented in CONTRIBUTING.md when written
