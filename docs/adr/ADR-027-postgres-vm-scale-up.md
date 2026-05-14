# ADR-027: Postgres VM Scale-Up — shared-cpu-2x + 2GB

**Status**: Accepted
**Date**: 2026-05-14

---

## Context

Satlas launched on Fly.io's unmanaged Postgres (`satlas-db-sjc`) sized
at `shared-cpu-1x` / 256MB. That was sufficient through MVP — the
catalog hovered around 6,000 satellites and the recompute sweep
completed inside the resource envelope without complaint.

As the active catalog grew toward 16,000 satellites
(SpaceX cadence + the GP `active` feed including more LEO objects),
the Postgres VM started showing sustained pressure. The TLE refresh
workflow at 12:38 UTC on 2026-05-14 produced three failures:

1. `planet` feed — urllib client read timeout (server too slow to respond)
2. `science` feed — HTTP 500
3. `visits/recompute` — HTTP 500

The server-side trace pointed at
`asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed
in the middle of operation`. The retry helper added in commit `f5ae914`
for transient asyncpg drops did not visibly fire — symptomatic of
sustained (not transient) pressure where every retry hits the same
overloaded backend.

Fly's machine health checks confirmed the diagnosis:

```
[✗] memory: system spent 1.53s of the last 10 seconds waiting on memory
[✗] cpu:    system spent 2.2s of the last 10 seconds waiting on cpu
[✗] io:     system spent 2.94s of the last 10 seconds waiting on io
```

The `vm` check had been critical for 8 hours 42 minutes — well past
"transient drop" territory. Connection-level checks (`pg` and `role`)
were still passing, so the Postgres process was alive but the
underlying VM was thrashing.

For comparison, the API and Celery worker VMs already sit at
`shared-cpu-2x` / 1GB (ADR-021); only the database remained at the
launch-day baseline.

---

## Decision

**Scale `satlas-db-sjc` to `shared-cpu-2x` with 2GB memory.**

Applied via:

```
flyctl machine update <machine-id> -a satlas-db-sjc \
  --vm-size shared-cpu-2x --vm-memory 2048
```

Post-update VM checks: all three wait counters at 0s/60s. Connection
pool, role, disk all passing.

The database volume is unchanged — only the machine size changed. No
data migration, no schema change, ~30 seconds of downtime during the
machine restart.

---

## Alternatives Considered

### A. Memory bump only (shared-cpu-1x + 1GB)

- **Pros**: Cheapest scale step (~$3-5/mo)
- **Cons**: Memory was the worst-pressure axis but not the only one —
  CPU wait was 2.2s/10s, I/O was 2.94s/10s. Memory alone leaves CPU
  bound. Probably trips again within a few weeks of catalog growth.
- **Rejected**: addresses the loudest symptom, not the whole envelope

### B. shared-cpu-2x + 2GB (chosen)

- **Pros**: Brings DB into line with API/worker sizing. Comfortable
  headroom for further catalog growth. CPU+memory+I/O all benefit.
- **Cons**: ~$10-15/mo additional cost
- **Accepted**: best balance of cost and headroom for 1-person ops

### C. Migrate to Fly Managed Postgres (`fly mpg`)

- **Pros**: Backups, HA, support, removes operational burden
- **Cons**: Significant migration effort (export, restore, secrets,
  connection-string rotation, downtime). Higher baseline cost. The
  unmanaged stack has been stable enough that the migration trigger
  isn't here yet.
- **Deferred**: revisit if operational pain accumulates (a second
  resource crisis within 90 days would be a trigger)

### D. Restart only

- **Pros**: Free, instant
- **Cons**: Clears accumulated state but doesn't change the underlying
  capacity. Would trip again within hours as load resumes.
- **Rejected**: addresses no root cause

---

## Consequences

### Positive

- TLE refresh + visits/recompute have headroom to complete reliably at
  current catalog size
- No more `asyncpg.ConnectionDoesNotExistError` storm during sweep
- DB sizing now consistent with API/worker
- Retry helper (`run_with_db_retry`) becomes effective again — it was
  designed for transient drops, not sustained overload

### Negative

- Monthly cost increase (~$10-15)
- Catalog is on an upward trend; we will likely revisit when the next
  saturation appears. Triggers to watch:
  - `vm` health check critical for > 30 min
  - Connection-pool exhaustion (>250 of 300 used)
  - Recompute exceeding 15 minutes consistently

### Operational follow-ups

- Sentry alerting on `asyncpg.exceptions.ConnectionDoesNotExistError`
  bursts (already captured; needs an alert rule)
- Periodic VM check review during the monthly runbook routine
  (added to ops note `루틴 점검`)
- If catalog reaches 30K+ or VM check tips again, reopen the managed-PG
  question (alternative C)
