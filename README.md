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

- Select a country on an interactive 3D globe
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
| Frontend | React · Vite · TypeScript · CesiumJS · satellite.js · turf.js |
| Infra | Docker Compose · Fly.io · Vercel · Upstash · Cloudflare · GitHub Actions |
| Data | CelesTrak (TLE) · Natural Earth (GeoJSON) |

---

## Data Sources

| Source | Purpose | License |
|---|---|---|
| [CelesTrak](https://celestrak.org) | TLE orbital elements for active satellites (fetched twice daily) | Free public service, no API key required |
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
- [x] `GET /satellites/overhead/{country_code}` — first MVP endpoint
- [x] Redis caching (60 s TTL per country, graceful degradation)
- [ ] Celery async task queue
- [ ] Frontend (CesiumJS globe + country selection)
- [ ] Deployment (Fly.io + Vercel)

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
