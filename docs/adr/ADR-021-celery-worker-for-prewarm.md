# ADR-021: Celery Worker for Overhead Prewarm

**Status**: Accepted
**Date**: 2026-05-10

---

## Context

ADR-020 introduced a per-country `/overhead` prewarm but rolled it out inside the API process. Within minutes of the production deploy users saw `502 Bad Gateway` across territories. The retrospect (Notion: "Prewarm 롤아웃 사고") identified two compounding causes:

1. **Thread-pool contention.** The prewarm sweep used `asyncio.to_thread` against the same default `ThreadPoolExecutor` (4 workers) the request handlers use. A single sweep over 200 countries kept those workers busy for minutes; large-territory requests (RU, CN) couldn't get a worker and Fly proxy returned 502.
2. **Memory pressure.** SATCAT cache + per-feed ingest buffers + warm_positions_cache + boundary caches were already close to the 512 MB limit; adding prewarm-induced object retention pushed over the cliff during TLE refresh.

The hotfix (commit `c5123cc`) registered the prewarm job out of the scheduler and kept the rest of ADR-020 (VM upgrade, sample 90 s, TTL 20 min, boundary fast-path). A follow-up commit (`c2b7083`) doubled VM memory to 1024 MB to stop the OOM cliff during TLE ingest. With those in place the service is stable but every cold-cache click still pays the lazy-path cost (~3-4 s for large countries on shared-cpu-2x).

The prewarm idea is sound — the failure was purely in *where* it ran. ADR-001 had already chosen Celery + Redis as the message-queue stack but no Celery code has been written yet; the project has been running on APScheduler in-process. This is the natural moment to actually wire Celery in.

---

## Decision

**1. Run prewarm in a Celery worker on a separate Fly machine.**

The API process owns request handling, the existing `warm_positions_cache` 60 s loop, and the `visits/recompute` admin endpoint. Anything else CPU-heavy and time-sliced moves to Celery.

```
fly app: satlas-api
 ├── process "app"     → uvicorn        (existing)
 ├── process "worker"  → celery worker  (new)
 └── process "beat"    → celery beat    (new, single instance)
```

Each process group is a separate Fly machine, so memory and CPU are isolated. The `app` machine stays on `shared-cpu-2x:1024mb`; `worker` and `beat` start on `shared-cpu-1x:512mb` each (cheap, scaled later if metrics demand).

**2. Celery broker + result backend = existing Redis (ADR-001).**

Same `REDIS_URL` env that already serves the cache. No new infrastructure.

**3. Beat schedule re-enables the 15-minute prewarm cycle from ADR-020.**

```python
beat_schedule = {
    "prewarm-overhead": {
        "task": "app.tasks.prewarm_overhead_all_countries",
        "schedule": timedelta(minutes=15),
    },
}
```

The task body is the same logic that lives in `scheduler.prewarm_overhead_job` today, moved to `app/tasks.py` and reframed as a Celery task. It loads the positions cache from Redis, iterates countries, runs `simulate_overhead_window`, and writes per-country payloads to the same `satlas:overhead:{cc}` keys the request handler reads. No API contract changes.

**4. Worker process registration removed from APScheduler.**

The hotfix's commented-out lines stay commented. APScheduler in the API process now owns only `warm_positions_cache` and TLE refresh — the lighter-weight jobs that don't conflict with request handling.

---

## Alternatives Considered

### A. Dedicated `ThreadPoolExecutor` in the API process
Keep prewarm in-process but give it its own executor (1 worker, prewarm-only) so request workers stay free.

Rejected: solves the thread-pool contention but not the memory contention. A 5-minute sweep still holds tens of MB of intermediate Python objects in the same heap as request handling. The post-fix retrospect was explicit that *both* axes broke; fixing one is a partial answer that invites another OOM cycle as the catalog grows.

### B. Worker process on the same Fly machine as API
Multi-process supervisor (e.g. `honcho`, or two `CMD` lines) running uvicorn and celery worker side by side on one VM.

Rejected: memory is shared across processes only at the kernel level (page-cache); user-space heaps don't share, so each process pays its own Python interpreter + dependency overhead. On a 1024 MB machine that's tight, and any future memory-hungry task brings the OOM risk back. Cost saving (~$3-5/mo) doesn't justify reproducing the failure mode we just fixed.

### C. Trigger prewarm from GitHub Actions (like TLE refresh)
GHA already runs ingest pushes and visits/recompute. Add a third schedule for prewarm.

Rejected: GHA cron granularity is fine for 12-h TLE refresh and 12-h visit precompute, but prewarm needs 15-min cadence to keep the 30-min window cache warm — that's 96 GHA runs/day per workflow, well into "abusing GHA as a job runner" territory. Also leaves no room for event-driven re-prewarm (e.g. immediately after a TLE refresh).

### D. Defer Celery, do A for now
Use the dedicated executor as a stopgap, defer the broader Celery rollout.

Rejected: the work to wire Celery once is roughly the work to wire it now. Doing A first means doing Celery later anyway when the next CPU-heavy background task lands (pass-history collation, dashboard precomputes). Two migrations vs one.

---

## Consequences

**Positive**
- Background sweeps cannot starve request handling, period — they run in a different process on a different machine.
- API memory pressure drops; the worker holds the prewarm-time intermediate objects.
- Celery is now actually present in the codebase, so the next background workload (pass history, telemetry roll-up) inherits the pattern instead of inventing a new one.
- Beat is single-instance by design (only one Fly machine in the `beat` group), so we don't need extra plumbing to prevent duplicate task fires.

**Negative**
- Two new Fly machines: `worker` and `beat`. Together ~$6-10/month at shared-cpu-1x:512mb each. Total monthly bill rises to roughly $10-15/mo (was ~$5 after ADR-020). Still well below paid-tier alternatives but worth noting as the project's first multi-machine architecture.
- Operational surface grows: deploy now affects three machines, log streams diverge, Sentry needs to be initialized in the worker process too. Worth the explicit "this is now a real distributed system" tax.
- Beat is a single point — if its machine is down, prewarm stops and lazy fallback takes over. Acceptable: the system degrades gracefully (back to ~3-4 s lazy responses), no data integrity issue.

---

## Notes

- The Celery task can reuse the existing `simulate_overhead_window` and `_visits_key` directly — they're pure functions over Redis + boundaries data and don't depend on the FastAPI request lifecycle.
- `app/celery_app.py` becomes the canonical place for future tasks. Keep it minimal at first: broker URL, beat schedule, autodiscover from `app.tasks`.
- Worker dependencies are the same as the API (`pyproject.toml` covers both); the Dockerfile entry-point is parameterized by Fly process group, no separate image needed.
- Sentry must be initialized in the worker boot path too — silent worker failures are worse than silent API failures because there's no user feedback loop.
- ADR-020's TTL of 20 minutes still pairs correctly with the 15-minute beat schedule: a missed beat tick can leave the cache empty for at most 5 minutes before the next tick refills.
- If the `beat` machine is overkill (one process holding only the beat scheduler), revisit by collapsing beat into the API process via `apscheduler` triggering a Celery `send_task`. Keep this as a possible Phase 2 simplification rather than a starting point — beat-as-its-own-process is the textbook Celery pattern and we're paying ~$3/mo to keep it textbook.

---

## Post-deploy adjustment — fan-out per country (2026-05-10)

The first production rollout of this ADR shipped a single beat-fired task that processed all 200 countries serially in one worker. Verification found the task running for 30+ minutes with `acknowledged: False` while only 4 country caches had been written; the task time limit didn't catch it cleanly and `task_acks_late=True` caused the broker to redeliver after each kill, producing an infinite-restart loop.

The work unit was simply too big for one Celery task on a `shared-cpu-1x` worker. Fixed by splitting into a fan-out:

- `prewarm_overhead_all_countries` (beat-fired): dispatches one `prewarm_overhead_one_country.delay(cc)` per loaded country, returns immediately. Effectively a queue-fill operation.
- `prewarm_overhead_one_country(cc)`: does the actual SGP4 simulation and cache write for one country. Each invocation finishes in seconds.

Effects:

- Workers process per-country tasks **in parallel** across processes — the two existing worker machines now actually share the load.
- A single hanging country no longer blocks the rest of the cycle; failures stay scoped.
- Hard-kill no longer applies in practice because individual tasks are short.
- Cache fills incrementally — users see fresh data as countries complete instead of waiting for the whole sweep.

Task-name compatibility was preserved (`app.tasks.prewarm_overhead_all_countries` still exists and is what beat fires), so any in-flight messages on the broker at deploy time still resolve to a registered handler. The task body is just radically smaller.

---

## Subsequent reversal — fan-out collapsed (2026-05-10, see ADR-022)

Later the same day, end-to-end measurement showed minor territories were still missing the cache. The fan-out wasn't the bottleneck — every per-country task was redoing identical SGP4 propagations, and a single `--concurrency=1` worker could not finish 234 of those before the 20-min cache TTL expired. Attempting to scale the worker (shared-cpu-2x, `--concurrency=2`) triggered Fly's burst-credit baseline drop and per-task time went *up* by 10-25×.

ADR-022 hoists propagation out of the per-country path entirely: one SGP4 batch over the whole catalog, then a polygon-only pass per country reusing those positions. Once that change landed, the per-country task was no longer slow enough to need fan-out; `prewarm_overhead_one_country` was removed and `prewarm_overhead_all_countries` became a single end-to-end sweep again — same task name beat already fires, just doing the whole job in-process.

The reasoning that drove the fan-out (long per-task SGP4 work blowing the time limit) was sound under the old work shape. Once the work shape changed, the fan-out's cost (per-task overhead, scattered cache state, harder failure attribution) outweighed the benefit. Architectural artifacts that solve a now-absent problem are still cost.
