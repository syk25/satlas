# Satlas

> 🌐 **English** · [한국어](README.ko.md)

**See which satellites are flying over each country, in real time.**

🛰️ Live: **[satlas.space](https://satlas.space)**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Live](https://img.shields.io/badge/live-satlas.space-7e14ff.svg)](https://satlas.space)
[![ADRs](https://img.shields.io/badge/architecture%20decisions-25-green.svg)](docs/adr/README.md)

<p align="center">
  <a href="https://youtu.be/F69mwx--Ojc">
    <img src="https://img.youtube.com/vi/F69mwx--Ojc/maxresdefault.jpg" alt="Satlas demo — click to play on YouTube" width="640" />
  </a>
  <br>
  <em>▶ Watch the demo on YouTube</em>
</p>

---

## Why Satlas

Existing satellite tracking tools answer one of two questions:

| Perspective | Representative Tools | Question Answered |
|---|---|---|
| Observer-based | Heavens-Above, Stellarium | "Can I see this satellite from my location?" |
| Ownership-based | UCS Satellite Database | "Which country built this satellite?" |

Satlas takes a third perspective — **country-based**:
*"Which satellites pass over this country, and when?"*

Before Satlas, answering this required walking through each satellite's orbit manually or fitting coordinate-based tools to a national boundary. Satlas reduces it to a single country click.

The seed came from an aircraft surveillance display I worked with in the Air Force, which shows aircraft activity around a country in real time. The framing — *what's flying over our airspace right now* — stuck with me. Years later, on a night walk, I noticed bright dots moving overhead. Most of them turned out to be satellites. Searching online, I found 3D globes that placed satellites in orbit and 2D tools that traced individual orbits, but nothing that answered the same question in satellite terms: *which satellites are over this country right now*. With launches accelerating, the gap felt worth filling.

---

## Features

- 🗺️ **Click any country** on a 2D world map → every satellite currently overhead
- 🏷️ **Filter by category** — Starlink, GPS, weather, science, military, ...
- 📅 **Upcoming passes for the next 24 hours**, grouped by 1 h / 6 h / 24 h windows
- 🛰️ **Track a satellite** — its real-time footprint and 95-minute ground track on the map
- 📊 **Global dashboard** — active catalog totals, category breakdown, most-overflown countries today, recent launches

---

## Screenshots

<p align="center">
  <img src="https://github.com/user-attachments/assets/3b79930d-ff64-42f8-b4c4-f1b883ffad21" alt="Overhead satellites for a selected country" width="800" /><br>
  <em>Click a country — every satellite currently overhead, with category filters and a 24-hour pass schedule.</em>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/35eb2f74-239d-4e34-9a8c-5b1c3c401165" alt="Global dashboard" width="800" /><br>
  <em>Dashboard — active catalog totals, category breakdown, most-overflown countries today, recent launches.</em>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/a367eafa-4f1c-4859-a2e6-290439e61c8b" alt="Tracking a single satellite" width="800" /><br>
  <em>Track a satellite — real-time position, footprint, and 95-minute ground track.</em>
</p>

---

## Tech Stack

| Layer | Technologies |
|---|---|
| Backend | Python 3.11 · FastAPI · PostgreSQL · Redis · Celery · APScheduler · SGP4 |
| Frontend | React · Vite · TypeScript · Leaflet · satellite.js |
| Infra | Docker Compose · Fly.io · Vercel · Vercel Edge Middleware · GitHub Actions |
| Data | CelesTrak (TLE + SATCAT) · Natural Earth (country polygons) |

---

## Architecture Decisions

Every significant architectural choice is recorded as an ADR — what was decided, what alternatives were rejected, and what trade-offs were paid. Full index: **[docs/adr/](docs/adr/README.md)** (25 ADRs).

Selected highlights:

- **[ADR-005](docs/adr/ADR-005-data-storage-strategy.md)** — TLE storage strategy: twice-daily snapshots + phased pre-computation
- **[ADR-014](docs/adr/ADR-014-deployment-platform.md)** — Deployment platform: Fly.io (backend) + Vercel (frontend)
- **[ADR-018](docs/adr/ADR-018-overhead-membership-refresh.md)** — Overhead refresh: server-side window prediction + client-side gating
- **[ADR-024](docs/adr/ADR-024-chunked-visits-recompute.md)** — Chunked recompute + Redis list schema (fixes the OOM cliff past 15k satellites)
- **[ADR-025](docs/adr/ADR-025-ip-geo-i18n-and-dynamic-og.md)** — IP-geo language pick + per-locale OG image variants

---

## Data Sources

| Source | Purpose | License |
|---|---|---|
| [CelesTrak](https://celestrak.org) | TLE orbital elements + SATCAT metadata (operator country, launch date, object type). Fetched twice daily as GP JSON | Free public service, no API key |
| [Natural Earth](https://www.naturalearthdata.com) | Country boundary polygons for satellite-over-country intersection | Public Domain |

Space-Track.org (US Space Force) is being evaluated as a supplementary historical TLE source and may be added in a future phase. Registration is free but required.

---

## Recent Milestones

- 🌐 **Custom domain** (satlas.space) + locale-aware OG image previews + first-visit IP-geo language pick — ADR-025
- 🔍 **SEO baseline** — robots.txt, sitemap.xml, JSON-LD WebApplication schema, Google Search Console
- 📋 **`/about` page** — friendly intro, sources, limits, privacy
- 📊 **Dashboard** — global catalog, category bars, top-overflown countries, recent launches
- 📅 **24-hour pass schedule** — 1 h / 6 h / 24 h grouping, panel tab toggle
- 💧 **Chunked recompute + Redis list schema** — bounds memory regardless of catalog size — ADR-024
- 🚀 **Public launch** — Fly.io + Vercel + GitHub Actions push model

---

## Target Users

- Space and satellite enthusiasts curious about what's overhead right now
- Students learning orbital mechanics, satellite operations, or space situational awareness
- Researchers analysing satellite pass patterns over specific countries

---

## Contributing

Contributing guidelines will be available in `CONTRIBUTING.md`.
Bug reports and feature requests are welcome via [Issues](https://github.com/syk25/satlas/issues).

---

## License

[MIT](LICENSE)
