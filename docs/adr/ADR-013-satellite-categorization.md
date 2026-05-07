# ADR-013: Satellite Categorization via CelesTrak Multi-Feed Ingestion

**Status**: Accepted  
**Date**: 2026-05-07

---

## Context

The initial TLE ingestion fetched from a single CelesTrak feed (`GROUP=active`), which returns ~15,000 tracked objects as a flat list with no metadata. The `orbit_class` and `category` columns in the `satellites` table were always NULL, making it impossible to filter or visually distinguish satellites by mission type or orbit.

Users observing the map had no way to tell whether a dot was an ISS, a GPS satellite, a military reconnaissance satellite, or space debris. The product goal — tracking satellites with specific missions over national territory — required classification.

---

## Decision

Ingest from **18 CelesTrak category-specific feeds** in addition to the `active` catch-all feed. Each feed maps to a `SatelliteCategory` enum value. Feeds are processed in priority order: specific categories first, `active` (→ `OTHER`) last.

**Category mapping:**

| CelesTrak group | Category |
|---|---|
| stations | STATION |
| weather, noaa, goes | WEATHER |
| military | MILITARY |
| amateur | AMATEUR |
| gps-ops, glo-ops, galileo, beidou | GNSS |
| starlink, oneweb, iridium, iridium-NEXT | COMMERCIAL |
| resource, planet | EARTH_OBS |
| science | SCIENTIFIC |
| active | OTHER (catch-all) |

**Orbit class** (`LEO` / `MEO` / `GEO` / `HEO`) is derived from TLE line 2 at ingestion time using mean motion and eccentricity — no external lookup required.

**Priority rule**: Once a satellite has a specific category (non-OTHER), subsequent feed processing cannot downgrade it to OTHER. A satellite seen in both `stations` and `active` keeps `STATION`.

---

## Alternatives Considered

### UCS Satellite Database
The Union of Concerned Scientists publishes a spreadsheet with operator, country, and purpose for ~2,000 active satellites. More detailed than CelesTrak's grouping.

Rejected: requires separate download pipeline, covers only ~13% of tracked objects, and is updated quarterly — too slow for our TLE refresh cadence.

### Name-pattern heuristics
Classify by matching satellite names against patterns (e.g., `STARLINK-*`, `GPS BIIR-*`).

Rejected: brittle, unmaintainable as constellations grow. CelesTrak's explicit grouping is the authoritative source.

### Single active feed + manual tagging
Keep one feed, allow admins to manually assign categories via API.

Rejected: not scalable at 15k satellites and not suitable for an open-source tool with no admin layer.

---

## Consequences

**Positive**
- All ~15k satellites get category and orbit class populated on first refresh.
- No external data dependency beyond CelesTrak (already used).
- Frontend can filter and color-code by category.

**Negative**
- Ingestion time increases from ~2 minutes to ~15 minutes per refresh cycle due to 18 sequential HTTP requests (0.5s polite delay between requests).
- CelesTrak has no official SLA; individual group feeds occasionally return stale or empty responses.
- Some satellites appear in multiple specific feeds (e.g., a weather sat in both `weather` and `noaa`). First feed wins; this is deterministic but may not always reflect the "best" label.

---

## Notes

- Ingestion is scheduled twice daily (00:00 / 12:00 UTC). The 15-minute runtime is acceptable within this cadence.
- Parallel fetching was considered but deferred due to CelesTrak rate-limiting risk (ADR backlog).
- The `satellite_category` Postgres enum is defined in migration `a1b2c3d4e5f6`.
