# Satlas

An open-source platform that provides satellite pass and dwell information by country and territory.

---

## Why Satlas

Existing satellite tracking tools answer one of two questions:

| Perspective | Representative Tools | Question Answered |
|---|---|---|
| Observer-based | Heavens-Above, Stellarium | "Can I see this satellite from my location?" |
| Ownership-based | UCS Satellite Database | "Which country built this satellite?" |

Satlas takes a third perspective — territorial:
"Which satellites pass over this country, and for how long?"

Previously, answering this question required checking each satellite's orbit individually or manually fitting coordinate-based tools to a national boundary. Satlas reduces this to a single country selection.

---

## Features

- Select a country on an interactive 2D world map
- View satellites currently passing over the selected country in real time
- Quantify dwell time per satellite
- Visualize theoretical observation footprint (nadir / horizon)
- Track pass count and next expected pass time
- Analyze the breakdown of satellites by operating country

---

## Tech Stack

| Layer | Technologies |
|---|---|
| Backend | Python 3.11 · FastAPI · PostgreSQL · Redis · Celery · APScheduler · SGP4 |
| Frontend | React · Vite · TypeScript · Leaflet · satellite.js |
| Infra | Docker Compose · Fly.io · Vercel · Cloudflare · GitHub Actions |
| Data | CelesTrak (TLE) · Natural Earth (GeoJSON) |

---

## Data Sources

| Source | Purpose | License |
|---|---|---|
| [CelesTrak](https://celestrak.org) | TLE orbital elements + object metadata (operator country, launch date) for active satellites; fetched twice daily as GP JSON | Free public service, no API key required |
| [Natural Earth](https://www.naturalearthdata.com) | Country boundary polygons for satellite-over-territory intersection | Public Domain |

Space-Track.org (US Space Force) is evaluated as a supplementary historical TLE source and may be integrated in a future phase. Registration is free but required.

---

## Roadmap

- [x] Project design and architecture documentation (ADR-001 – ADR-011)
- [x] Backend scaffold (FastAPI · PostgreSQL · Redis · Docker Compose)
- [x] Database schema (SQLAlchemy ORM + Alembic migrations)
- [x] CI/CD pipeline (GitHub Actions, path-based triggers)
- [x] TLE ingestion pipeline (CelesTrak on-demand)
- [x] SGP4-based position calculation and country boundary intersection
- [x] `GET /satellites/overhead/{country_code}` — overhead satellites by country
- [x] `GET /satellites/positions` — all satellite positions (global map view)
- [x] Redis caching (positions cache 60 s warm cycle, per-country overhead cache 20 min TTL, graceful degradation)
- [x] Scheduled TLE ingestion (GitHub Actions push model, twice daily at 00:00 / 12:00 UTC — ADR-015)
- [x] Frontend MVP (Leaflet 2D map · country click · satellite markers · i18n en/ko)
- [x] Deployment (Fly.io + Vercel)
- [x] Background prewarm pipeline (Celery worker + beat, single batched SGP4 sweep every 15 min, sub-2 s response across all 234 territories)
- [x] `GET /satellites/passes/{country_code}` — 24-hour pass timeline per country
- [x] Pass schedule UI (panel tab, 1 h / 6 h / 24 h grouping)
- [x] `GET /stats/dashboard` — global stats (active satellites by category, top territories by 24h passes, recent launches)
- [x] Dashboard page at `/dashboard` (React Router) with category, top-countries, and recent-launches cards

---

## Target Users

- Space and satellite researchers, students
- Defense and security professionals
- Researchers who need to analyze satellite pass patterns over specific territories

---

## Boundary Data & Disclaimer

Country boundaries are sourced from [Natural Earth](https://www.naturalearthdata.com/). Some territories have disputed borders or contested sovereignty. Satlas does not take a political position on any territorial dispute. Boundary representations follow Natural Earth conventions and may not reflect all competing claims.

Satellite data is available for all regions, including disputed territories. Users are responsible for interpreting data in accordance with applicable laws and their own assessment of territorial status.

---

## Contributing

Contributing guidelines will be available in `CONTRIBUTING.md`.
Bug reports and feature requests are welcome via [Issues](https://github.com/syk25/satlas/issues).

---

## License

[MIT](LICENSE)
