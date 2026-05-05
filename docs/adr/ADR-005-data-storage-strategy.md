# ADR-005: Data Storage Strategy — TLE Snapshots + Phased Pre-computation

- **Status**: Accepted
- **Date**: 2026-05-06

## Context

Satlas requires two types of satellite data:

1. **Current position data**: Used for real-time display on the globe
2. **Historical pass data**: Used for dwell time analysis, pattern tracking, and trend queries

The choice of how to store and compute this data has major implications for storage cost, query performance, and system complexity.

## Decision

### TLE Storage

Store raw TLE snapshots from CelesTrak twice daily.

- ~9,000 satellites × 170 bytes × 2 snapshots/day = ~1.5MB/day
- Annual accumulation: ~550MB/year
- Cost: ~$0.08/month (Fly.io PostgreSQL at $0.15/GB)

TLE snapshots enable historical orbit reconstruction. Without them, there is no way to retroactively calculate where satellites were in the past.

### Real-time Position

Calculated **client-side** using `satellite.js` in the browser. The server delivers TLE data only; the browser computes current positions using SGP4. This offloads computation from the server entirely.

### Historical Pass Data — Phased Approach

**Phase 1 (MVP)**: On-demand calculation + Redis cache

- User requests "passes over Korea last month" → calculate from stored TLE snapshots
- Cache result in Redis (24-hour TTL)
- Acceptable at low traffic; repeated queries for popular countries served from cache

**Phase 2 (Growth)**: Pre-computation on TLE ingestion

- Every time TLE is ingested → calculate pass events for all countries → store in DB
- Estimated storage: ~6,000 LEO satellites × 195 countries × ~1 pass/day × 100 bytes ≈ 117MB/day → ~43GB/year
- Cost: ~$6.50/month at maturity
- Queries become simple DB lookups

### Pre-computed Pass Event Schema (Phase 2)

```
passes (
  satellite_id,
  country_code,
  entry_time,
  exit_time,
  max_elevation,
  duration_seconds
)
```

Indexed on: `(country_code, entry_time)`, `(satellite_id, entry_time)`

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| No historical storage | Zero cost | No historical analysis possible |
| Pre-compute everything from launch | Fast queries immediately | High complexity for MVP |
| **Phased approach (chosen)** | Simple MVP, scalable later | Transition work required at Phase 2 |
| Third-party historical API | No storage needed | Cost, dependency, data gaps |

## Consequences

- TLE snapshot storage begins at launch — this is the foundation for all historical features
- Phase 1 Redis cache must be designed with Phase 2 pre-computation in mind (same data shape)
- Historical data API (pass history queries) is a viable paid feature once Phase 2 is active
- Space-Track.org provides historical TLE as an alternative/supplement to self-accumulated data
