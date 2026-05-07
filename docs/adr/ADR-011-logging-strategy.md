# ADR-011: Logging Strategy — structlog, JSON in Production

- **Status**: Accepted
- **Date**: 2026-05-06

## Context

Before writing the first endpoint, the logging format and library must be decided. This affects how operational issues are diagnosed in production and how the codebase reads for contributors.

## Decision

**Use `structlog` with environment-based output format.**

- `ENVIRONMENT=development` → colored, human-readable console output
- `ENVIRONMENT=production` → structured JSON (one log event per line)

## What to Log

| Level | Events |
|---|---|
| `INFO` | TLE ingestion complete (satellite count, duration), pass calculation complete (country, cache hit/miss) |
| `WARNING` | Unexpected but handled situations (e.g., TLE parse failure for a satellite) |
| `ERROR` | Unhandled exceptions, 5xx responses |

Not logged: individual satellite positions (too noisy), all DB queries (use SQLAlchemy `echo=True` in development only).

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| stdlib `logging` | No extra dependency | Verbose configuration, JSON requires additional setup |
| `loguru` | Clean API, simple | JSON output needs a plugin |
| **`structlog` (chosen)** | JSON and colored output built-in, environment-switchable | One additional dependency |

## Consequences

- `structlog>=24.0` added to dependencies
- `ENVIRONMENT` added to `.env.example` (`development` / `production`)
- Log configuration initialised once at application startup in `app/main.py`
- SQLAlchemy `echo` flag driven by `ENVIRONMENT`, not a separate setting
