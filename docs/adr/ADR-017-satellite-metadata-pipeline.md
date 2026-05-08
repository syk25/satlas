# ADR-017: Satellite Metadata Pipeline — CelesTrak GP JSON + SATCAT

**Status**: Accepted
**Date**: 2026-05-09

---

## Context

ADR-013 established `category` and `orbit_class` from CelesTrak's group feeds. The remaining metadata users want in the satellite detail panel — operator (US, PRC, INTELSAT, …), launch date, decay date, international designator (`1998-067A`), object type (PAYLOAD vs ROCKET BODY vs DEBRIS), and RCS size — was still left NULL on every row.

The first attempt assumed CelesTrak's GP JSON endpoint (`gp.php?FORMAT=json`) carries this metadata alongside TLE lines. It does not. GP JSON returns only OMM mean elements (mean motion, eccentricity, inclination, …) plus `OBJECT_NAME`, `OBJECT_ID`, `NORAD_CAT_ID`. The CelesTrak source for satellite metadata is a separate file: `satcat.csv`.

Two consequences followed from that initial misreading:

- TLE lines aren't in GP JSON either. The previous TLE-format ingest produced two raw line strings; the new path needs to synthesize them from OMM.
- Per-row metadata can't ride along with each group feed; SATCAT has to be fetched separately and joined on NORAD ID.

A side issue surfaced during user review: the column originally named `operator_country` actually holds SATCAT's `OWNER` value, which contains country codes (`US`, `PRC`) **and** organization codes (`INTELSAT`, `PLAN`, `SES`). "Country" is a misnomer for the column's contents.

---

## Decision

**1. Two-source ingestion, joined on NORAD ID.**

GitHub Actions (already used for TLE ingest per ADR-015) now fetches both feeds before pushing them to the backend:

| Source | URL | Purpose |
|---|---|---|
| GP JSON per group | `gp.php?GROUP={group}&FORMAT=json` | Orbital elements (OMM) |
| SATCAT (single file) | `pub/satcat.csv` | Per-NORAD metadata |

SATCAT is pushed first to `/admin/satcat/ingest`. The backend parses the CSV into a process-memory dict keyed by NORAD ID. Subsequent `/admin/tle/ingest/{group}` calls join each upserted satellite against this dict.

**2. TLE lines synthesized from OMM via `sgp4.exporter`.**

`Satrec` is initialized from the OMM dict (`sgp4.omm.initialize`); `sgp4.exporter.export_tle` produces canonical 69-character line1/line2 strings. Downstream code (DB column type, frontend `satellite.js`) keeps consuming TLE strings unchanged.

**3. Column and field rename: `operator_country` → `operator`.**

The DB column, the API response field, and the UI label are renamed. `operator_name` (free-text full name, currently NULL pending a UCS-DB integration) and `operator_type` (enum) keep their names; the rename only affects the SATCAT-sourced field.

**4. Object-type enum bucketing.**

SATCAT abbreviates `OBJECT_TYPE` as `PAY` / `R/B` / `DEB` / `TBA`; we map these to `PAYLOAD` / `ROCKET_BODY` / `DEBRIS` / `UNKNOWN`. SATCAT's `RCS` column is a numeric area in m²; we bucket using CelesTrak's standard breakpoints: <0.1 m² = `SMALL`, 0.1–1.0 m² = `MEDIUM`, >1.0 m² = `LARGE`.

---

## Alternatives Considered

### Backend fetches SATCAT directly
The server polls `pub/satcat.csv` on a timer instead of receiving it from GHA.

Rejected: the same datacenter-IP friction that drove ADR-015's push model applies. SATCAT is occasionally rate-limited too; routing through GHA runners reuses the established path.

### Persist SATCAT to DB or Redis instead of process memory
A `satcat` table or Redis hash would survive restarts.

Rejected for now: SATCAT is read-only enrichment data with a 12-hour refresh cadence (matching TLE refresh). On restart, `_SATCAT_CACHE` is empty until the next GHA run; until then, `_upsert_entries` falls back to leaving fields NULL, but DB rows from the previous run still hold the metadata. The blast radius of a cold-start gap is one ingest cycle's worth of new satellites — small enough not to warrant added persistence machinery.

### Keep `operator_country` and document the misnomer
Leave the column name and explain in code comments that it covers organizations too.

Rejected: the misnomer would propagate into every new caller, and the column is exposed in the API response. Renaming once is cheaper than re-explaining indefinitely.

### Add `operator_name` from UCS Satellite Database now
UCS provides full operator names (`SpaceX`, `NASA`, `China Aerospace Science and Industry Corp.`) for ~2,000 active satellites.

Deferred: separate ingest pipeline, NORAD-ID join logic, and license review. SATCAT alone covers all 16k+ satellites with a usable code; full names are a Phase-2 enhancement.

---

## Consequences

**Positive**
- All four metadata fields (`operator`, `launch_date`, `object_type`, `international_designator`) populate at 100% on tracked satellites; `decay_date` and `rcs_size` populate where SATCAT has the values.
- The UI's PAYLOAD-default filter from the previous commit is now meaningful — `object_type` is no longer always NULL.
- The `operator` field surfaces both state actors (`US`, `PRC`) and commercial operators (`INTELSAT`, `PLAN`) without claiming a country attribution that doesn't exist.

**Negative**
- One additional 6.5 MB CSV fetch per refresh cycle (twice daily). Negligible compared to the existing 15 MB of TLE data.
- Process-memory cache means SATCAT is unavailable for the first ingest after a cold start; new satellites in that window get NULL metadata until the next refresh repopulates them.
- CSV parse + 68k-row dict build runs on the event loop; benchmarked at ~2 s on a `shared-cpu-1x` machine. Acceptable as a 12-hourly admin operation but would need offloading to a thread if the cadence increased.

---

## Notes

- Migration `33b5ddba1a03` performs the column rename in-place (`ALTER COLUMN ... RENAME TO`) — no data loss.
- Migration `3d6183811fdf` adds `decay_date`, `international_designator`, `object_type` (enum), and `rcs_size` (enum).
- `parse_satcat_csv` is exported so tests can drive it directly without HTTP. The endpoint at `/admin/satcat/ingest` is a thin wrapper.
- The `_OBJECT_TYPE_MAP` includes `TBA` (CelesTrak's "to be assigned") mapped to `UNKNOWN`. Encountered in practice for newly-launched objects awaiting catalog review.
