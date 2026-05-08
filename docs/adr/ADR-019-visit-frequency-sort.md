# ADR-019: Visit Frequency Sort — 24-hour Pass Count per Country

**Status**: Accepted
**Date**: 2026-05-09

---

## Context

ADR-018 introduced a 30-minute forward simulation per country to fix the membership-refresh problem. While solving that, two things became clear:

1. **Dwell time is not a meaningful sort dimension.** A LEO satellite passes over any given country in 5–15 minutes, and the duration is determined mostly by orbital geometry (inclination versus territory latitude, footprint radius) — not by the satellite's identity or mission. Sorting by dwell time produces a near-uniform list.

2. **Visit frequency is the meaningful dimension.** How often a satellite passes over a territory varies sharply between satellites — it depends on inclination, altitude, sun-synchronicity, and constellation membership. "Satellites that pass over our territory most often = satellites with the most observation opportunities." Frequency is the closest honest proxy for "observation pressure" that public TLE data can give.

Implementing visit frequency requires the same forward-simulation primitive as ADR-018 but with a longer window. This ADR scopes the 24-hour variant and surfaces it as a sort option in the panel.

---

## Decision

**1. 24-hour forward window, computed eagerly.**

After every TLE ingest cycle (12-hourly, ADR-015), a background task runs a 24-hour SGP4 simulation across the active satellite catalog and counts entry events per (country, satellite) pair. The first request after an ingest is served immediately from cache; lazy first-request computation is rejected (see Alternatives).

**2. Algorithm: per-satellite ground track precompute + STRtree spatial join.**

For each satellite, sample 1,440 positions at 60-second intervals across `[now, now + 24h]`. For each sampled point, query a `shapely.strtree.STRtree` of country polygons to find which territory contains the sub-satellite point. Counting entry events (outside→inside transitions) per (country, satellite) yields the pass count.

Cost characteristics:

| Stage | Operations | Estimated time |
|---|---|---|
| SGP4 propagation | 16k × 1,440 = 23M | ~3 minutes (≈10 µs/call) |
| STRtree contains | 23M × O(log N) | ~2 minutes |
| Total per ingest cycle | — | ~5 min, runs as background task |

**3. Storage: per-country Redis hash.**

```
satlas:visits:24h:{country_code}  →  HASH { norad_id → pass_count }
```

TTL 14 hours — slightly longer than the 12-hour ingest cadence so a missed ingest doesn't strand stale-but-valid data. The hash is rebuilt wholesale each cycle, not incrementally.

**4. API exposure: extend `/overhead/{country_code}` response.**

Each `SatelliteOverhead` row gains a `passes_24h: int | None` field — `None` if the precompute hasn't completed for this country yet (cold start grace), otherwise the count. The frontend uses this for sorting; no new endpoint is added.

**5. UI: sort toggle in the panel.**

Add a sort selector with two options:

- **Entry time** (default, current behavior) — preserves ADR-018 semantics: satellites currently overhead first, then by upcoming entry.
- **Visit frequency ↓** — descending by `passes_24h`. Surfaces "satellites that pass over us most often."

Default stays at Entry time so existing user behavior isn't disrupted; visit frequency is opt-in.

---

## Alternatives Considered

### A. 7-day window
A weekly count is more stable (averages out daily orbital geometry quirks).

Rejected: 7× the compute (~35 min per cycle), and the result barely changes day-to-day for most satellites — the daily 24h count is already representative because orbits are deterministic over short horizons. Daily granularity also lets users see immediate effects when a constellation launches new birds.

### B. Lazy first-request computation per country
First request to `/overhead/{cc}` triggers the 24-hour simulation if cache is cold; subsequent requests use the cache.

Rejected: ~2-minute first-request latency is unacceptable for an interactive panel. Per-country lazy computation also loses the "same simulation, all countries" amortization — re-running SGP4 200 times for the same satellite is wasteful when one shared sample sweep covers everyone.

### C. Direct (territory × satellite) sampling
For each country, for each satellite, sample 1,440 points and check polygon containment.

Rejected: 200 × 16k × 1,440 = 4.6B containment tests. Two orders of magnitude more expensive than the per-satellite STRtree approach.

### D. Make visit frequency the default sort
Replace entry-time sorting with frequency sorting.

Rejected for now: changes existing user behavior without warning. Visit frequency is more analytical and less situationally useful — most users glancing at the panel want "what's overhead now," not "what comes here often." Toggle-based opt-in is gentler. Reconsider if telemetry shows the toggle is heavily used.

### E. Pre-compute only for top-N popular countries
Maintain a hot list (e.g., top 20 by request volume) with eager computation; others are lazy.

Rejected: adds complexity (request counting, hot-list selection, eviction) for a marginal win — the per-satellite sweep already amortizes across all countries, so the marginal cost of computing every country is just the STRtree containment work, which is the cheaper half.

---

## Consequences

**Positive**
- Sort by frequency answers "which satellites observe us most" more honestly than dwell time or "currently overhead" can.
- No first-request latency penalty; cache is always warm post-ingest.
- Same simulation primitive as ADR-018; the 30-minute window simulation continues to operate independently for membership, while this 24-hour pass builds on the same SGP4 + boundaries layer.
- Single shared sweep amortizes across all 200 countries — adding new territories costs only STRtree containment, not extra propagation.

**Negative**
- ~5 minutes of background CPU per ingest cycle (twice daily). Not interactive; runs after TLE upsert completes.
- Cold-start gap: between server boot and the first post-boot ingest, `passes_24h` is `None` and the sort option is unavailable for affected countries. The frontend handles this by graying out the toggle when the field is null for the loaded list.
- Adds one more eagerly-computed Redis structure to evict on schema changes; document in `services/cache.py` keyspace registry.

---

## Notes

- Pass count is defined as the number of *entry* events into the territory polygon during the window, not the number of sampled points inside. A 5-minute pass with five 60-second samples inside counts as one pass, not five.
- Sun-synchronous Earth-observation satellites typically yield 2 passes per 24h at a given mid-latitude territory (one ascending, one descending node). High-inclination Starlink shells yield 4–6. Equatorial communications constellations may yield zero. These regularities are good sanity checks for the implementation.
- The STRtree is built once at module load (boundaries already loaded as a dict; we wrap them in STRtree). Rebuild on country-data refresh — currently never, but capture the dependency.
- Observability: log per-cycle timing and total event count; Sentry-tag any cycle that exceeds 10 minutes wall time so we catch regression early.
- This ADR does not touch dwell-time computation; ADR-018's 30-minute membership window remains the source of truth for entry/exit times. Visit frequency is a separate dimension.
