# ADR-014: Deployment Platform — Fly.io (Backend) + Vercel (Frontend)

**Status**: Accepted
**Date**: 2026-05-08

---

## Context

Moving Satlas to its first production deployment required choosing a hosting platform for both the FastAPI backend and the React frontend, plus the supporting Postgres and Redis services. The constraints were free-tier first, low operational overhead for a one-developer project, and compatibility with the always-on workloads (the TLE refresh scheduler runs every 12 hours and the positions pre-cache job every 60 seconds — see ADR-016).

---

## Decision

| Component | Platform | Reason |
|---|---|---|
| Backend API | Fly.io | Always-on VMs, in-region Postgres/Redis available via Fly CLI |
| Frontend | Vercel | Auto-deploy from GitHub, global CDN |
| Database | Fly Postgres | Same VPC as the API, minimal latency |
| Redis | Fly Redis (Upstash-managed) | Provisioned via Fly CLI, no separate account |

### Deployment flow

```
local code
  ├── git push → GitHub
  │     ├── Vercel (auto-detect frontend changes)
  │     └── GitHub Actions → fly deploy (when backend/ or fly.toml changes)
  └── fly deploy (manual, for emergency releases)
```

The GHA backend job is path-scoped to `backend/` and `fly.toml`; frontend changes route exclusively through Vercel.

---

## Alternatives Considered

### Neon (serverless Postgres) instead of Fly Postgres
Auto-suspend with on-demand wake-up would have been free indefinitely, but the cold-start of 1–3 s collides with the 60-second positions pre-cache (ADR-016) and the every-15-minute TLE scheduler — under load, the scheduler would frequently hit a sleeping DB and race the wake-up. Fly Postgres is always on.

### Render or Railway for the backend
Either would work, but Fly's region-pinned machines and integrated CLI for both Postgres and Redis kept the operational surface smaller. Free tier on Fly covers two `shared-cpu-1x` machines, which fits the API + Postgres pair.

---

## Consequences

**Positive**
- All backend infrastructure (API + DB + Redis) lives behind one CLI and one billing account.
- Frontend deploys are independent — frontend bugs can't roll back the API and vice versa.
- Free tier comfortably covers MVP scale: 2 of 3 free Fly VMs in use, 1 GB of 3 GB free volume.

**Negative**
- Ties the project to Fly's regional availability. A regional outage takes the API down; mitigated only by upgrading to multi-region (paid).
- TLE snapshots grow ~180 MB/month, giving roughly 1.5 years on the 3 GB free volume before action is needed.

---

## Notes — Deployment-time issues encountered

Three Fly-specific behaviors surfaced during the rollout. Detailed root-cause writeups live in the project's "lessons learned" page; here is the summary so future readers know what to watch for:

- **Postgres URL scheme**: `postgres://` from `fly pg attach` must be rewritten to `postgresql+asyncpg://` for SQLAlchemy's async driver.
- **asyncpg + sslmode**: asyncpg does not accept the libpq `sslmode` query parameter — use `connect_args={"ssl": False}` for the in-VPC connection.
- **HA multi-instance startup race**: when two replicas boot in parallel, the seeding inserts collide on the unique NORAD ID index. Switched to ON CONFLICT UPSERT to make seeding idempotent.

### Region revision (2026-05-08)

Initial deployment used the NRT (Tokyo) region for proximity to Korean users. CelesTrak was found to block the `active` feed (~46,000 satellites, 2.5 MB) for NRT data-center IPs — the API ingested only 1,420 satellites instead of ~16,000.

**Diagnosis**: `curl` from an SJC machine returned 200 / 2.5 MB / 2.4 s; the same call from NRT hung. The asymmetry only became visible after response bodies and error types were added to the structured log output.

**Resolution**: switched `primary_region = "sjc"` and redeployed. Trade: ~30 ms → ~150 ms latency to Korean users in exchange for the full satellite catalog. ADR-015 later replaced server-side fetching entirely with a GitHub Actions push model, making the region choice less load-bearing for ingest.
