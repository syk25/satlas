# ADR-016: Satellite Positions Pre-cache

**Status**: Accepted
**Date**: 2026-05-08

---

## Context

`/satellites/overhead/{country_code}` originally loaded all 16,789 active satellites from the database on every request and ran SGP4 propagation sequentially in the async event loop. The CPU-bound work blocked the event loop, so a single overhead request stalled every other in-flight request, and the first overhead request after a cold start took 10+ seconds to respond.

---

## Decision

A background scheduler computes positions for the entire active catalog every 60 seconds and stores them in Redis under `satlas:positions:all` (TTL 120 s — a full second cycle of slack so the cache never expires before the next refresh). The overhead endpoint reads this cached list and runs only the polygon-containment filter per request.

```
scheduler (60 s)
  └── warm_positions_cache():
        ├── SELECT 6 columns × 16k rows from DB
        ├── asyncio.to_thread(SGP4 propagate × 16k)   ← off the event loop
        └── SET satlas:positions:all = JSON, EX=120

overhead request
  └── GET satlas:positions:all → polygon filter only → response
```

The scheduler also re-warms immediately after each TLE ingest cycle so the post-ingest 503 window — where the DB has new TLEs but the cache still holds the previous propagation — is eliminated.

---

## Alternatives Considered

### A. On-demand SGP4 in a thread pool
Move propagation off the event loop with `asyncio.to_thread()` but compute on demand. Resolves the event-loop blocking but does not address the 10-second per-request CPU cost — every cold-cache request still pays full price.

### B. Filter to PAYLOAD-only by default
Restrict the default catalog to operating satellites (~1,400 rows) so per-request SGP4 is fast. Hides too much from the user (no Starlink visualization, no debris awareness) and only kicks the can — once `include_inactive=true` is selected, the original cost returns.

### C. Pre-cache in DB rather than Redis
Materialized view refreshed on a timer. Possible but harder to invalidate fast, and adds a Postgres dependency for what is fundamentally a hot-path read cache.

C was rejected as over-engineered for a 16k-row position cache that fits comfortably in a few MB of Redis JSON. A is rejected because B's per-request cost is the actual bottleneck, not just the event-loop blocking.

---

## Decision Rationale

- **First-request response is fast.** Every request hits a warm cache.
- **Event loop is fully unblocked.** SGP4 work runs in a thread pool inside the scheduler, never inside a request handler.
- **60-second staleness is acceptable.** TLEs themselves refresh every 12 hours (ADR-015); a 60-second propagation lag is well below the noise floor of the underlying mean elements.
- **No UX trade-off.** Unlike alternative B, the full catalog remains queryable at the same per-request latency.

---

## Consequences

**Positive**
- p95 latency on `/overhead/*` dropped from ~10 s to <100 ms.
- The cache is shared across all clients — load is amortized to a single sweep per minute regardless of concurrent users.
- Adding new SGP4-derived endpoints (e.g., the global positions feed used by the world map) is now cheap because they read the same cache.

**Negative**
- Up to 60 s of position lag at cache boundaries. Frontend animation interpolates on top via `satellite.js`, so the visible jitter is bounded.
- A scheduler failure stops position updates. The 120 s TTL means stale data is served (rather than 503) for one extra cycle, then the cache expires; mitigated by Sentry alerting on scheduler errors.
- The cache key `satlas:positions:all` collides easily — the `/positions` endpoint had to switch its derivative key suffix from `:all` to `:full` to avoid clobbering the master cache.

---

## Notes

- Implementation: `tle_ingest.warm_positions_cache()` runs the SGP4 sweep; `scheduler.py` registers it under an `IntervalTrigger(seconds=60)` plus a one-shot 10-second-after-startup trigger so cold starts are warm within 10 seconds.
- The cached payload includes only the columns the overhead endpoint needs (6 SAT columns + 2 TLE columns), keeping memory ~5× smaller than hydrating the full ORM rows.
- ADR-018 (membership refresh) and ADR-019 (visit-frequency precompute) both build on this cache: the 30-min and 24-h forward simulations reuse the warm `t=0` positions instead of recomputing them.
