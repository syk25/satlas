# ADR-001: Message Queue — Celery + Redis instead of RabbitMQ

- **Status**: Accepted
- **Date**: 2026-05-06

## Context

RabbitMQ was included in the initial stack candidates. After analyzing Satlas's actual async processing requirements, the choice was reconsidered.

Async processing needs in Satlas:
1. Periodic TLE ingestion (CelesTrak)
2. Batch calculation of satellite passes and dwell time per country
3. User-requested pass prediction calculation

## Decision

**Do not adopt RabbitMQ. Replace with Celery + Redis.**

Redis is already in the stack for TLE caching and real-time satellite position pub/sub. Celery can use Redis as a broker, so async task queue capability is gained without adding a new service.

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| RabbitMQ | Proven message broker, supports complex routing | Requires a new service, unnecessary at Satlas scale |
| **Celery + Redis (chosen)** | No new service, Redis roles consolidated | Expands Redis single-point-of-failure scope |
| FastAPI BackgroundTasks | Simplest option | Tasks lost on process restart, no monitoring |
| APScheduler alone | Simple, sufficient for schedule-based tasks | Cannot handle user-request-triggered async tasks |

## Consequences

- A single Redis instance covers three roles: cache + pub/sub + Celery broker
- Reduced infrastructure complexity (fewer Docker Compose services)
- If Redis reaches its limits, the Celery broker can be swapped to RabbitMQ with a configuration change only
