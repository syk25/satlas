# Satlas — User Flows

## UI User Flow

### 1. Landing
- User lands on the globe view
- Real-time satellites visible, orbiting on the globe
- No login required

### 2. Country Selection
- User rotates the globe and clicks a country
- Country boundary highlighted (land territory, Natural Earth)
- Side panel opens: list of satellites currently over the selected country
- Filter options: operator country, orbit class (LEO / MEO / GEO)
- Each satellite shows: name, NORAD ID, operator country, orbit class, current dwell time

### 3. Satellite Detail (from country view)
- User clicks a satellite in the list
- Satellite detail panel: specs (operator country, orbit class, launch date)
- Theoretical observation footprint toggled on globe (geometric coverage, not imaging capability)
- Historical pass list for this satellite over this country (time range selector)
- Predicted upcoming passes

### 4. Historical Analysis
- User sets a time range (default: last 7 days, max: available TLE snapshot history)
- Pass history loads: entry time, exit time, dwell duration per pass
- Anomaly flag visible if predicted vs actual pass deviated significantly

### 5. Search
- User searches by satellite name or NORAD ID
- Results link to satellite detail view

### 6. Bookmarks (requires login)
- User bookmarks a country or a specific satellite
- Bookmarked items accessible from profile

---

## API User Flow

Target users: researchers, defense analysts, developers integrating Satlas data into their own systems.

### Priority 1 — MVP (country-centric)

| Use Case | Description |
|---|---|
| Current satellites over a country | "Which satellites are over South Korea right now?" |
| Historical passes by country | "Which satellites passed over Japan in May 2026, and for how long?" |
| Predicted passes by country | "Which satellites will pass over Taiwan in the next 7 days?" |

### Priority 2 — MVP support (satellite lookup)

| Use Case | Description |
|---|---|
| Satellite detail | "Give me specs for NORAD ID 25544" |
| Satellite list | "List all active LEO satellites operated by China" |

### Priority 3 — Phase 2 (satellite-centric)

| Use Case | Description |
|---|---|
| Satellite pass history by satellite | "Which countries did this satellite pass over last month?" |
| Reverse lookup | "Which satellites were overhead at 37.5°N 127°E at 14:00 UTC on May 1?" |

---

## Key Design Constraint

Territorial waters are not included in MVP boundary polygons (land territory only, Natural Earth). The intersection engine is data-source-agnostic — maritime boundaries can be added later without code changes. See ADR-003.
