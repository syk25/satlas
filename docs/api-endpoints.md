# Satlas API Endpoints

All endpoints follow REST conventions. Base URL: `https://api.satlas.io`

Authentication: Public endpoints require no auth. Protected endpoints require a JWT Bearer token.

---

## MVP Endpoints

### 1. Current satellites overhead

```
GET /satellites/overhead/{country_code}
```

Returns satellites currently over the specified country's territory.

**Path parameter**
- `country_code` — ISO 3166-1 alpha-2 (e.g. `KR`, `US`)

**Response** (array)
```json
{
  "norad_id": 25544,
  "name": "ISS (ZARYA)",
  "operator_country": "US",
  "operator_name": "NASA",
  "operator_type": "GOVERNMENT",
  "orbit_class": "LEO",
  "line1": "1 25544U ...",
  "line2": "2 25544 ...",
  "entry_time": "2026-05-06T14:00:00Z"
}
```

`line1` / `line2`: TLE lines for client-side position calculation via satellite.js.
`entry_time`: used by the frontend to compute current dwell duration.

---

### 2. Historical pass events by country

```
GET /passes/{country_code}?start=&end=
```

Returns actual pass events for the specified country within the given time range.

**Path parameter**
- `country_code` — ISO 3166-1 alpha-2

**Query parameters**
- `start` — ISO 8601 datetime (required)
- `end` — ISO 8601 datetime (required)

**Response** (array)
```json
{
  "satellite": {
    "norad_id": 25544,
    "name": "ISS (ZARYA)",
    "operator_country": "RU",
    "operator_name": "Roscosmos",
    "operator_type": "GOVERNMENT",
    "orbit_class": "LEO"
  },
  "entry_time": "2026-05-01T09:12:00Z",
  "exit_time": "2026-05-01T09:22:00Z",
  "duration_seconds": 600,
  "entry_lat": 37.5,
  "entry_lon": 126.9,
  "exit_lat": 35.1,
  "exit_lon": 129.0,
  "anomaly_flag": false
}
```

---

### 3. Predicted pass events by country

```
GET /passes/{country_code}/predicted?start=&end=
```

Returns predicted pass events within the specified future time range (max 7 days from now).

**Path parameter**
- `country_code` — ISO 3166-1 alpha-2

**Query parameters**
- `start` — ISO 8601 datetime (required)
- `end` — ISO 8601 datetime (required, max 7 days from start)

**Response** (array)
```json
{
  "satellite": {
    "norad_id": 25544,
    "name": "ISS (ZARYA)",
    "operator_country": "US",
    "operator_name": "NASA",
    "operator_type": "GOVERNMENT",
    "orbit_class": "LEO"
  },
  "entry_time": "2026-05-07T14:03:00Z",
  "exit_time": "2026-05-07T14:13:00Z",
  "duration_seconds": 600,
  "entry_lat": 37.5,
  "entry_lon": 126.9,
  "exit_lat": 35.1,
  "exit_lon": 129.0,
  "predicted_at": "2026-05-06T00:00:00Z"
}
```

---

### 4. Satellite detail

```
GET /satellites/{norad_id}
```

Returns metadata for a single satellite.

**Path parameter**
- `norad_id` — NORAD catalog number (integer)

**Response**
```json
{
  "norad_id": 25544,
  "name": "ISS (ZARYA)",
  "operator_country": "US",
  "operator_name": "NASA",
  "operator_type": "GOVERNMENT",
  "orbit_class": "LEO",
  "launch_date": "1998-11-20",
  "is_active": true
}
```

---

### 5. Satellite list

```
GET /satellites?operator_country=&operator_name=&operator_type=&orbit_class=&is_active=
```

Returns a filtered list of satellites.

**Query parameters** (all optional)
- `operator_country` — ISO 3166-1 alpha-2
- `operator_name` — partial match (e.g. `SpaceX`)
- `operator_type` — `GOVERNMENT` / `MILITARY` / `COMMERCIAL` / `INTERNATIONAL`
- `orbit_class` — `LEO` / `MEO` / `GEO` / `HEO`
- `is_active` — `true` / `false`

**Response** (array of satellite objects, same shape as satellite detail)

---

## Phase 2 Endpoints

| Endpoint | Description |
|---|---|
| `GET /satellites/{norad_id}/passes?start=&end=` | Pass history for a specific satellite across all countries |
| `GET /satellites/overhead?lat=&lon=&at=` | Satellites overhead at a specific coordinate and time |

---

## Authentication

Protected endpoints (bookmarks, user preferences) require:
```
Authorization: Bearer <jwt_token>
```

Issued via OAuth2 (GitHub / Google). See ADR-006.

---

## Rate Limiting

Applied at the Cloudflare layer. Public API is rate-limited per IP.
Details TBD when pricing tier is defined.
