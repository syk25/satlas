# ADR-022: Hoist SGP4 propagation out of per-country prewarm

**Status**: Accepted
**Date**: 2026-05-10

---

## Context

Same-day follow-up to ADR-021. After ADR-021's per-country fan-out went live, end-to-end measurement revealed two soft failures.

1. Cache-hit responses for large territories (CN/US/RU) sat at 1.3-2.2 s. Investigation traced it to wire-time (1.2 MB JSON across KR↔SJC) plus an unnecessary Pydantic round-trip in the cache-hit path. Both fixed in a single push (gzip middleware + `Response(content=cached, ...)` shortcut + `beat_init` kickstart so deploy doesn't leave a 15-min cold gap). Large territories settled to 0.7-0.8 s under HTTP/2 connection reuse.

2. Once those wire-side issues were out of the way, sampling a wider set of territories surfaced a deeper problem: minor countries (MG, TV, IS, MN, etc.) were still paying the lazy 4-5 s path on every first click, regardless of how long the worker had been running. The 200+ per-country fan-out tasks on a single `--concurrency=1` worker were not finishing a full sweep inside the 20-min cache TTL.

A follow-on attempt to scale the worker (shared-cpu-2x:1024 MB, `--concurrency=2`) made things visibly worse: per-task `elapsed` jumped from ~4 s to 50-110 s as soon as both prefork workers warmed up. Fly's shared-CPU plans burn through burst credits when both vCPUs are pegged, and CPU-bound SGP4 sustained at full pace pegs everything onto the baseline share — each process effectively dropped to ~1/16 of a core. The bigger VM cost more and produced a 10-25× slowdown per task. Reverted immediately.

That left the budget question on the table: more CPU was not the answer.

Looking at the work itself, the per-country task does this for every country:
- Pre-filter ~5000 active payload satellites by orbital reach.
- Propagate each surviving candidate at every sample time across the 30-min window (~21 samples at 90 s spacing).
- Polygon-containment check at each sample to detect entry/exit.

Step 2 — SGP4 propagation — is identical for every country. With ~234 countries, a single sweep does ~10 M propagations of which 99.5% are duplicates of work some other country task already did or will do.

---

## Decision

**1. Hoist propagation. Compute window positions for every active payload once per sweep.**

New function `compute_window_positions(candidates, now, ...)` runs the SGP4 batch and returns each candidate dict enriched with a `samples` list of `(t, lat, lon)` tuples. The t=0 entry reuses the snapshot lat/lon already in the positions cache, so propagation runs only at t > 0.

**2. Drop SGP4 from the per-country path.**

New function `find_overhead_in_window(country_code, window_positions, request_time)` does the same work as `simulate_overhead_window` minus the SGP4 — it walks the pre-computed samples and runs polygon containment + the existing entry/exit pair search.

**3. Collapse the fan-out back into a single task.**

`prewarm_overhead_one_country` is removed. `prewarm_overhead_all_countries` now does the whole sweep:

1. Load all positions, filter to PAYLOAD only.
2. Call `compute_window_positions` once for the whole catalog.
3. For each loaded country, call `find_overhead_in_window`, build the `SatelliteOverhead` payload, write `satlas:overhead:{cc}`.

Total work per sweep is one SGP4 batch (~5 K × 21 = ~100 K calls) plus one polygon-only pass per country. Local benchmark on 15 K satellites and 234 countries: 36 s vs the old 273 s estimate. Production projection on shared-cpu-1x baseline: 5-8 min per sweep, comfortably inside the 15-min beat cycle and 20-min TTL.

The lazy path in the request handler (`simulate_overhead_window` for cache misses on a single country) is left untouched — it already pays only the per-country cost, and it falls back to a non-issue once prewarm keeps the cache warm.

---

## Alternatives Considered

### A. Increase worker CPU
Move the worker VM to shared-cpu-2x or performance-cpu-2x and bump concurrency.

Rejected. Already attempted at shared-cpu-2x — 10-25× per-task slowdown from Fly's burst-credit baseline drop. Performance-cpu-2x would solve the contention but at +$15/mo for what is fundamentally redundant work. Reducing the work itself is strictly cheaper.

### B. Cache window positions in Redis, fan-out reads them per task
Pre-compute once, then every per-country task pulls the same ~10 MB blob from Redis to do its polygon pass.

Rejected. Each task would now block on a multi-MB Redis read, undoing the savings — for a worker with `--concurrency=1` there is no parallelism to win, and the cache-thrashing is pure overhead.

### C. Reduce sample density (e.g. 90 s → 180 s spacing)
Halves SGP4 work without restructuring.

Rejected. Trades correctness (entry/exit timing accuracy) for performance, and the dedup approach gives a much larger reduction without that trade-off. ADR-020 already moved 60 s → 90 s; pushing further would surface visible misses on fast LEO crossings.

### D. Pre-compute all-country positions and ship them to clients
Skip the per-country layer entirely; let the browser do polygon checks.

Rejected as a different architecture. ADR-005 and ADR-018 chose server-side membership for a reason (clients see the territory list, not the satellite catalog). Out of scope.

---

## Consequences

**Positive**
- One sweep finishes in minutes instead of failing to finish at all under load. All 234 territories stay within the 20-min cache TTL.
- Worker memory pressure drops. The intermediate `window_positions` list is large (~10 MB), but it lives for the duration of a single task and shares the polygon STRtree the worker already loads.
- The fan-out machinery is gone. `prewarm_overhead_one_country` removed; the test for that task removed; the celery `worker_prefetch_multiplier=1` precaution is no longer load-bearing but kept as defensive default.
- ADR-021's failure mode (the original single-task version blowing the time limit) is preempted at the source — total work per sweep is now small enough that going back to a single task is the right answer.

**Negative**
- One task is now larger in scope. If `compute_window_positions` itself fails, the whole sweep fails for that cycle (instead of fan-out's per-country isolation). Mitigated by a 15-min beat cycle: a missed sweep is recovered next tick. Hard time limit and soft time limit retained from ADR-021.
- The `samples` field doubles intermediate memory per satellite during the sweep. Fits comfortably in the 512 MB worker, but should be revisited if the active catalog size grows substantially.
- `simulate_overhead_window` is now used only by the lazy path in the request handler. It duplicates logic that is also expressible as `compute_window_positions(...)` + `find_overhead_in_window(...)`. Kept as-is for now because the lazy path doesn't benefit from batched propagation (one country at a time), but it's a candidate for future consolidation.

---

## Notes

- Result parity verified locally before deploy: identical NORAD ID sets across the old per-country path and the new precompute path for CN, US, KR, MG, TV.
- The post-deploy production sample of 20 territories (mixed sizes) hit 19/20 under 1.5 s with HTTP/2 connection reuse; SD remained at 2.6 s, dominated by response transfer rather than server time. Documented in the trouble-shooting log as a separate (non-prewarm) follow-up track.
- The reverted worker upgrade left a useful artifact in fly.toml's worker comment block: shared-CPU concurrency is a trap for sustained CPU work. Worth keeping as a written reminder.

---

## Post-deploy adjustment — worker memory 512MB → 1024MB (2026-05-10)

The original ADR claimed the hoisted `window_positions` array fits comfortably in a 512MB worker. That estimate was wrong — production hit a SIGKILL loop within an hour. The samples data itself (~10MB) was small, but the worker's resident baseline (boundary STRtree ~50MB + Celery main + Python interpreter ≈ 250-300MB) plus per-task simulation scratch pushed the prefork child over the cliff every fork. Logs showed `Process 'ForkPoolWorker-NNN' pid:XXXX exited with 'signal 9 (SIGKILL)'` repeating to ForkPoolWorker-790 before being caught.

Fix: bump the worker `[[vm]]` memory from 512MB to 1024MB. CPU class (shared-cpu-1x) and concurrency (=1) stay — the parallelism path was already ruled out under "Alternatives Considered". Cost increase ~$1-2/mo.

Recovery measurement:
- Worker sweep log: `prewarm sweep complete: 234 countries in 216.67s (propagation 3.06s, polygon+cache 213.61s total)`. 3.6 min per cycle, well inside the 15-min beat schedule.
- 9-territory sample (BT, UY, SD, IS, TV, MG, KR, US, CN): all under 1.5 s. SD, which had been the lone 2.6 s outlier in the prior sample, came back at 0.49 s.

Adds an extra lesson: a local memory measurement does not represent the production resident baseline. New workloads need at least one production RSS observation before sizing the VM.
