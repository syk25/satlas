# ADR-010: Testing Strategy — Real Database, No Mocks

- **Status**: Accepted
- **Date**: 2026-05-06

## Context

Before writing the first endpoint, the testing approach must be defined. The key decision is whether API tests use a real PostgreSQL database or a mocked/in-memory substitute.

## Decision

**Use a real PostgreSQL test database (`satlas_test`). No DB mocks.**

### Test Levels

| Level | Target | Database |
|---|---|---|
| Unit | SGP4 calculation, polygon intersection logic | None |
| Integration | API endpoints (full request → DB → response) | Real PostgreSQL (`satlas_test`) |

### Test Database Lifecycle

- A separate `satlas_test` database is used — isolated from the development database
- Alembic migrations run at test session start
- Each test runs inside a transaction that is rolled back after the test completes — no persistent state between tests
- `TEST_DATABASE_URL` environment variable configures the connection

### CI Environment

GitHub Actions runs a PostgreSQL 15 service container alongside the test job. No external database is required.

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| Mock DB | Fast, no setup | Migrations are never tested; mock/prod divergence can hide real failures |
| Shared dev DB | Simple | Tests pollute development data; CI has no dev DB |
| **Separate test DB (chosen)** | Isolated, tests real migrations, CI-friendly | Requires PostgreSQL in CI (solved by service containers) |

## Tools

- `pytest` + `pytest-asyncio` — async test runner (already in dev dependencies)
- `httpx` — async HTTP client for endpoint tests (already in dev dependencies)
- No additional packages required

## Priority

Per CLAUDE.md: core logic first.

1. SGP4 calculation correctness
2. Polygon intersection (satellite over country boundary)
3. MVP API endpoints

## Consequences

- `TEST_DATABASE_URL` must be set in local `.env` and CI environment
- GitHub Actions `ci-backend.yml` runs a PostgreSQL 15 service container
- DB mocks are not permitted in this codebase
