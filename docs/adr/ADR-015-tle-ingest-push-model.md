# ADR-015: TLE Ingestion via GitHub Actions Push Model

**Status**: Accepted
**Date**: 2026-05-08

---

## Context

CelesTrak's `active` feed (~46,000 satellites, 2.5 MB) returned HTTP 403 when fetched from the production Fly.io machines. The first hypothesis was a regional issue, so the deployment region was migrated NRT → SJC (ADR-014). This did not solve the problem — the block applies to Fly's data-center IP ranges generally, not just one region.

Without the `active` feed, the database held only ~1,420 satellites instead of the expected ~16,000, leaving the overhead endpoint nearly empty.

---

## Decision

The backend no longer fetches from CelesTrak directly. Instead, GitHub Actions runners (which use non-data-center IPs) pull each feed and push it to the API:

```
GHA runner (non-DC IP) → CelesTrak download
        ↓
POST /admin/tle/ingest/{group}   (Bearer token auth)
        ↓
backend: parse + bulk UPSERT → DB
```

The cron schedule lives in `.github/workflows/tle-refresh.yml`: runs at 00:00 and 12:00 UTC daily, sequencing all category feeds (stations, weather, GNSS, military, EO, …, then `active` last as the catch-all).

Authentication uses a single shared admin token (`ADMIN_TOKEN`) stored as a GitHub Secret and verified by the API on every push.

---

## Alternatives Considered

### Region change
Already attempted (NRT → SJC). Fly's IP ranges are blocked across regions for high-volume CelesTrak feeds; not a regional issue.

### Direct SSH-based seeding
Run the fetch from a developer laptop and SSH the data into the production DB. Rejected: not reproducible, not automatable, and brittle (sessions break mid-transfer).

### Space-Track.org
Authoritative TLE source with an account-based API. Rejected for now because it adds account management, rate-limit handling, and a more complex auth flow for marginal data quality benefit at this stage.

### Cloudflare Worker proxy
Run a Worker that fetches CelesTrak and forwards to the API. Workable but adds another moving part for no benefit over GHA, which already runs on schedule, has secrets management, and gives free observability via the Actions UI.

---

## Companion changes

### Bulk UPSERT
Per-row inserts produced multi-hour ingest times for 16k+ rows. Replaced with chunked `INSERT … ON CONFLICT … DO UPDATE` (500 rows per batch — well under Postgres' 65k parameter ceiling). The `active` feed now ingests in ~30 seconds.

### DB connection stabilization
Added `pool_pre_ping=True` and `pool_recycle=1800` to the SQLAlchemy engine config. Long-running background ingest jobs were holding stale connections and failing on the first query of each cycle.

---

## Consequences

**Positive**
- The API is no longer responsible for outbound CelesTrak traffic. Reduces the IP-based failure mode to zero.
- GHA gives free scheduled retries, free secrets management, and free observability.
- Bulk UPSERT also makes the seed path idempotent — replays of a feed don't double-insert.

**Negative**
- Adds a build-system dependency (GHA) to a runtime data-pipeline. If GHA is down or the workflow misconfigures, the catalog goes stale silently until someone notices.
- Token-based auth on a public endpoint requires careful secret rotation discipline.

---

## Notes

- The push endpoint (`POST /admin/tle/ingest/{group}`) is path-scoped per feed group; `active` is treated as the catch-all and processed last so more specific category labels (e.g., `gps-ops` → GNSS) win over the generic OTHER label.
- ADR-017 later extended this model with a parallel SATCAT push endpoint for satellite metadata enrichment.
- Lesson for future external-data integrations: `curl` from a production-equivalent IP before designing the ingest path. If the source blocks data-center ranges, design around a non-DC environment from day one rather than retrofitting.
