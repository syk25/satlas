# ADR-024: Chunked visits/recompute + Redis list storage

**Status**: Accepted
**Date**: 2026-05-13

---

## Context

ADR-019 introduced `/admin/visits/recompute`: a once-per-12h sweep that
walks every active satellite's 24-hour ground track, finds pass events
(entry/exit per country), and persists per-country results to Redis. The
overhead endpoint reads the counts (`satlas:visits:24h:{cc}`) to enrich
its response; the new pass schedule UI (added in commit 93af6e9) reads
the event list (`satlas:passes:24h:{cc}`).

The sweep was implemented as a single batch:

1. `_fetch_position_rows(db)` returns the full ~16,000-row catalog as a list.
2. `compute_24h_passes(satellites)` accumulates every event across every
   satellite in a single `dict[cc, list[event]]` (~80,000 events) and
   returns it.
3. `store_passes(passes)` JSON-serialises each country's list and writes
   one `SET satlas:passes:24h:{cc}` per country, plus one `HSET` per
   country for the visit counts.

For the production catalog this trips an 860MB RSS peak on the API VM,
which has a 1024MB cap. OOM-Kill of uvicorn was observed mid-sweep:

```
Out of memory: Killed process 646 (uvicorn) total-vm:1569692kB,
anon-rss:860284kB
```

After the kill, GHA's `urllib.request.urlopen` to the admin endpoint
returns `HTTP 502 Bad Gateway`, the visits hashes land empty or partial
(only the first 8 of 234 country writes completed in the most recent
case), and the pass schedule UI shows "no passes" for every country.

Memory attribution from the same crash:

| Source | Estimated bytes |
|---|---:|
| Sentry per-request transaction (12-min span chain, ASGI integration) | ~100 MB |
| ORM row materialisation (16k × 12-col tuples, TLE strings ~70 B each) | ~50 MB |
| `compute_24h_passes` events dict accumulation | ~16 MB |
| STRtree boundary + prepared geometries | ~50 MB |
| SGP4 / shapely transient working sets (GC-lagged) | ~50–80 MB |
| Concurrent request handling + uvicorn base | ~200 MB |
| Headroom before OOM | ~400 MB |

The events dict is *not* the dominant cost. The dominant cost is the
combination of (a) holding the full 16k-row result set during the
~12-minute walk, (b) accumulating a single Sentry transaction for the
duration, and (c) Python's lag-collecting the per-iteration transient
objects produced by SGP4 propagation and shapely Point queries. Any
fix targeting only the events dict would have left most of the RSS
problem untouched.

---

## Decision

**1. Stream the catalog instead of materialising it.**

`stream_position_rows(db, chunk_size=1000)` issues the same SELECT through
a PG server-side cursor (`db.stream(...).partitions(1000)`) and yields
row batches. The previous `_fetch_position_rows` stays for callers that
already hold the full set in memory (e.g. `warm_positions_cache`, which
JSON-serialises the entire catalog anyway).

**2. Compute and persist per chunk.**

`recompute_visits` becomes:

```text
begin_recompute(country_codes)         # clear stale keys
async for chunk in stream_position_rows(db, 1000):
    sats = chunk_to_satellites(chunk)  # filter PAYLOAD + unwrap Enum
    passes = compute_24h_passes(sats)  # one chunk's events only
    store_passes_chunk(passes)         # HINCRBY + RPUSH in one pipeline
    del chunk, sats, passes
    gc.collect()
```

Peak chunk memory: ~1,000 satellites × (TLE strings + metadata) ≈ 1 MB,
plus that chunk's events (≈ 5,000 × 250 B = 1.3 MB). The explicit
`del + gc.collect()` is load-bearing — without it CPython's generational
collector holds shapely Point / SGP4 satrec objects across chunks and
RSS climbs monotonically anyway.

**3. Redis schema change — passes from JSON blob to Redis list.**

Old: `SET satlas:passes:24h:{cc}` value = `[{event1}, {event2}, ...]` as
a single JSON string. Required the entire country's events to be in
memory before the write.

New: Redis list of JSON-encoded events, one element per pass. Chunked
recompute appends with `RPUSH key event1_json event2_json ...` per
chunk; the `/satellites/passes/{cc}` endpoint does `LRANGE 0 -1` and
concatenates the elements back into a JSON array. Each element is
self-contained (carries name + category + orbit_class + timestamps), so
neither writer nor reader has to parse the existing data to extend it.

Visit counts (`satlas:visits:24h:{cc}`) stay as a hash but are now
updated via `HINCRBY` per (cc, norad_id) rather than `HSET` wholesale,
because chunks discover events incrementally.

**4. Clean-slate at the start of each sweep.**

`begin_recompute(country_codes)` deletes every `satlas:visits:24h:*` and
`satlas:passes:24h:*` key up front. Without this, HINCRBY would
accumulate counts across consecutive sweeps; with it, each sweep starts
from zero and the running totals correctly reflect *this* recompute's
walk. The short window of empty per-country data (until the first chunk
that touches a country lands) is acceptable because the GHA cron is the
only writer and the dashboard / passes UI both already handle empty
lists gracefully.

**5. End the Sentry transaction at the handler entry.**

The first line of `recompute_visits` calls
`sentry_sdk.get_current_scope().transaction.finish()`. A 12-minute span
chain under sentry-asgi's default sampling accumulates enough metadata
to OOM on its own (~100 MB observed). Uncaught exceptions still reach
Sentry via the framework's global exception handler — we only lose the
detailed trace for the admin sweep itself, which we never investigated
anyway.

**6. Chunk size 1,000.**

Picked empirically. Smaller chunks (250) trade memory for Redis
round-trips and add latency under in-region (~ms) Redis. Larger chunks
(5,000) creep back toward the all-at-once memory shape that the change
exists to avoid. 1,000 satellites × ~5 passes ≈ 5,000 events per chunk
fit comfortably under any reasonable per-chunk cap.

---

## Alternatives Considered

### A. Bump the API VM from 1024 MB to 2048 MB
Simplest fix — one line in `fly.toml`, ~$3/month extra.

Rejected as the permanent solution but kept as the contingency. The
memory-bump path assumes the catalog won't grow; once active payloads
cross ~30,000 (Starlink alone is on track), the next OOM is back. The
streaming refactor is bounded by the chunk size, not the catalog size,
so it future-proofs without recurring cost. Bumping memory is the
cheap fallback we'd take if `RECOMPUTE_CHUNK_SIZE = 1000` ever turns
out to leak somewhere we can't measure.

### B. Move `visits/recompute` to the Celery worker
The worker (separate VM, 1024 MB, concurrency=1) already runs the
15-minute prewarm sweep. Moving the recompute alongside it would
isolate the long compute from the request-handling VM.

Rejected. Concurrency=1 serialises prewarm and recompute — when a
recompute lands, prewarm pauses for 12 minutes, missing two cycles.
Acceptable but not free. More importantly, it doesn't fix the memory
shape; it just relocates it. If recompute OOMs the worker, the prewarm
queue piles up and dashboard performance degrades. Streaming fixes
the root cause regardless of which machine holds it.

### C. Pre-gzip the cache blob to reduce JSON memory
Wouldn't help. The OOM comes from the *Python object graph* during the
compute walk, not from the serialised output. The output JSON for the
biggest country (~150 KB) was never the issue.

### D. Use Redis Streams instead of a List
Redis Streams support consumer-group semantics for processing pipelines.
Overkill — we're not consuming, we're snapshotting. Lists give us O(1)
RPUSH and a single LRANGE read on the hot path.

---

## Consequences

**Positive**

- Memory peak for `recompute_visits` drops from ~860 MB (OOM) to a
  bounded ceiling proportional to `RECOMPUTE_CHUNK_SIZE`, not catalog
  size. Catalog can grow 2–3× before chunk size needs revisiting.
- The passes endpoint serves cache hits in roughly the same time
  (LRANGE on a few thousand elements is sub-ms on in-region Redis).
- The chunked path is also a natural place to add progress logging
  (per-chunk counts) — future operability win.

**Negative**

- One extra DB round-trip pattern (server-side cursor). The asyncpg
  driver supports this natively; no infrastructure change. The
  cursor is held for the full 12 minutes, which means one connection
  pool slot is unavailable to other endpoints for the duration. The
  pool is sized for 10 concurrent connections, so this is a 10%
  capacity hit on the API VM during recompute. Acceptable — the
  recompute runs once per 12h and a 90% pool is plenty for normal
  traffic.
- Redis schema change. The previous `SET` blob can stay around until
  TTL expires (~14h after the last write); after that, only the new
  `LIST` path is read. No migration script.
- HINCRBY semantics differ from HSET if the same `(cc, norad_id)`
  appears across multiple chunks. In practice each satellite only
  appears in one chunk (the row stream doesn't duplicate), so this
  is not an issue. If row duplication ever surfaces (e.g. a TLE
  snapshot replicated in error), the count would be inflated.
- Losing the per-sweep Sentry transaction means we can't trace timing
  of individual chunks in the Sentry UI. Logs still carry the elapsed
  time per chunk; the trade is acceptable.

---

## Notes

- The first deployment of this change is `commit-pending`. Production
  measurement is added below once the next GHA cycle exercises the
  new path.
- The single-batch `compute_24h_passes` and `store_passes` are
  retained for unit tests and any small-input internal caller. They
  are *not* called by `recompute_visits` anymore.
- If chunk-size tuning turns out to matter, `RECOMPUTE_CHUNK_SIZE`
  in `app/routers/admin.py` is the single knob.
- This is the second OOM-driven architectural change in the recompute
  path (ADR-022 was the first, for the prewarm sweep). Both shared the
  pattern of "single-pass accumulation that worked at 5,000 satellites
  but breaks at 16,000". The next time we add a long-running compute,
  designing it streaming from the start is cheaper than refactoring
  later.
