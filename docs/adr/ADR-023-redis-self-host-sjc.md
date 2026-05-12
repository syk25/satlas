# ADR-023: Self-Hosted Redis in sjc (replaces cross-Pacific Upstash)

**Status**: Accepted
**Date**: 2026-05-12

---

## Context

ADR-001 fixed Redis as the cache + Celery broker. The actual Redis instance was provisioned through `flyctl redis create` (Fly's Upstash integration) some time before this ADR, and quietly ended up in `sin` (Singapore) — the region default at the moment of creation. The API runs in `sjc`. Nobody noticed, because day-to-day requests served small responses (a few KB) and the per-byte network cost across the Pacific was hidden in the noise.

The cost surfaced as soon as cache values grew. After ADR-022 hoisted SGP4 propagation, each `satlas:overhead:{cc}` cache value for large territories landed at 1.0-1.6 MB of JSON. Every cache hit then required pulling 1+ MB from Singapore to San Jose over a single TCP stream. The bandwidth-delay product on that path (RTT ~180 ms, single-stream TCP window) capped throughput at ~25 KB/s, so:

- `satlas:overhead:US` (1.16 MB): ~44 s per cache GET
- `satlas:overhead:RU` (1.6 MB): ~60 s per cache GET
- `satlas:overhead:CN` (1.17 MB): ~42 s per cache GET
- Small territories (KR, JP): 1-2 s — slow but tolerable; obscured the systemic issue

User-visible click-to-render time tracked the GET cost exactly. None of the code optimisations from earlier in the same week (gzip middleware, Pydantic shortcut, ADR-022 SGP4 dedup, beat_init kickstart, worker memory bump) were visible to end users because every cache read was waiting on trans-Pacific TCP.

Direct probe from the app machine confirmed:

| Probe | Result |
|---|---:|
| `PING` to Upstash sin | ~181 ms |
| `GET` 1 MB key | 2.1-42 s (variable; possibly some Upstash throttling on repeated heavy reads) |

The 2-42 s range itself hints that this isn't pure TCP physics — Upstash likely also rate-limits or shapes traffic — but the floor is set by the trans-Pacific path regardless. Moving Redis into `sjc` resolves both axes.

---

## Decision

**1. Run Redis as a self-hosted Fly app in `sjc`.**

A new Fly app, `satlas-redis`, runs `redis:7-alpine` on a `shared-cpu-1x:256mb` machine in `sjc`. Connection from `satlas-api` (also `sjc`) goes through Fly's private 6PN network at `satlas-redis.internal:6379`. Both apps belong to the same org, so traffic is internal-only and free of egress.

Infrastructure config lives at `infra/redis/` (Dockerfile + fly.toml) — outside `backend/` so the repo's primary build pipeline isn't entangled with it.

**2. Cache-only persistence model.**

Redis is configured with `--save '' --appendonly no` — no RDB snapshots, no AOF. The data is entirely reconstructible:

- `satlas:positions:all` rebuilds every 60 s from the `warm_positions_cache` APScheduler job
- `satlas:overhead:{cc}` rebuilds every 15 min via the Celery prewarm sweep (ADR-022)
- `satlas:passes:24h:{cc}` and `satlas:visits:24h:{cc}` rebuild on the GHA `visits/recompute` cron (~12 h)

A Redis restart loses everything; full warm cache returns within ~5 min. Disk I/O for persistence would be pure overhead given that recovery time.

**3. Authentication via secret.**

`REDIS_PASSWORD` (48 hex chars) is set as a Fly secret on the Redis app and injected into the `requirepass` directive at process start. The same password is encoded into `satlas-api`'s `REDIS_URL` secret. Rotating the password = `flyctl secrets set` on both apps + restart.

`--protected-mode no` is set because Fly's 6PN is already a private network — clients are limited to the org's apps. Public bind is impossible without explicit `[http_service]` or service ports exposed via the proxy, which we don't configure.

**4. Eviction policy: `allkeys-lru` with `maxmemory 200mb`.**

The data set is small (~50 MB observed). The eviction policy is set defensively in case any future cache addition grows unexpectedly; we'd rather evict cold keys than have writes start failing. The 256 MB VM has headroom past the 200 MB cap for Redis's own bookkeeping.

---

## Alternatives Considered

### A. Move to Upstash via `flyctl redis create --region sjc`
Same managed service, but provisioned in the right region.

Rejected for cost. The smallest plan listed by `flyctl redis plans` is "Fixed 250 MB" at $10/mo. The cheapest self-host equivalent is ~$2-3/mo for a shared-cpu-1x:256mb machine. For a cache that the prewarm sweep can rebuild in 5 min, the $7-8/mo gap doesn't buy useful resilience.

### B. Pre-gzipped cache values (defer the Redis move)
Store cache values already gzipped to cut bytes-on-the-wire 5-10×.

Rejected as the primary fix. It would have brought US cache reads from ~44 s to ~5 s — better, but still bad. The underlying constraint was the network path, and any cache value that grows in the future (multi-MB pass histories, future overlays) would hit the same wall. Fixing the path solves the class of problem; fixing one symptom doesn't.

The pre-gzip idea remains valid for a future micro-optimization (Issue #7) but no longer urgent.

### C. Self-host Redis as a process inside `satlas-api`
Add a Redis process group to `satlas-api`'s `fly.toml`, sharing machines.

Rejected. ADR-021 separated the Celery worker and beat from `satlas-api` precisely so memory and CPU footprints don't entangle. Reverting to co-location for Redis would put the same kind of cliff back in front of us: a Redis memory spike would now also threaten request handlers and the prewarm worker.

### D. Just wait for Upstash to "calm down"
The earlier 2-42 s variance on the same probe suggested some throttling. Maybe behaviour would improve overnight.

Rejected. Even at the floor, 2 s for a single GET is two orders of magnitude slower than what's possible on the same machine pair. Hoping for a non-deterministic improvement isn't a fix.

---

## Consequences

**Positive**
- Cache GET for 1 MB drops from 42 s to ~20 ms — a 2,000× improvement on the worst case. Median user request returns to the design budget of "fast, regardless of country size".
- The Redis path is now under our control: we can grow the data set, tune eviction, and audit usage without filing tickets to a managed provider.
- Cost change: $0 (current Upstash pay-as-you-go bill was small) to ~$2-3/mo. Manageable.
- All code optimisations from the previous days (gzip, Pydantic shortcut, ADR-022 dedup) are finally user-visible.

**Negative**
- Operational surface adds one more Fly app. Health monitoring (Issue #9 already covers DB, will need to extend to Redis) and on-call considerations grow.
- No automatic backups. Acceptable because data is reconstructible, but if we ever cache anything *not* reconstructible (e.g., user-generated state), this assumption needs re-examination.
- Single-machine setup. No replication, no failover. If the Redis machine dies mid-day, API responses fall back to lazy compute (4-5 s per request) until prewarm refills the cache. Acceptable degradation, but logged as a known limitation.

---

## Notes

- The first deploy of the Redis app bound only to IPv4 (`--bind 0.0.0.0`). Fly's 6PN is IPv6-only — the bind has to include `::` for inter-app connections to land. Caught immediately by the first probe from satlas-api. Adding `0.0.0.0 ::` to the bind list resolved it.
- `flyctl redis` is still the Upstash integration — there's no native "Fly Redis" managed service. The `flyctl apps create ...` path is the only self-host option.
- Old Singapore Upstash instance is retired in the same change via `flyctl redis destroy`. It coexisted with the new self-hosted Fly app (also named `satlas-redis`) because Upstash add-ons and Fly apps don't share a name space — the Upstash hostname was `fly-satlas-redis.upstash.io`, the self-host one is `satlas-redis.internal`.
- ADR-001 still stands: Redis remains the cache + Celery broker. This ADR only changes the *location* and *operational model* of the Redis instance, not the choice of Redis itself.
