# Project Charter — Satlas

## Overview

**Project**: Satlas
**Started**: 2026-05-06
**Type**: Open Source (MIT)
**Repository**: https://github.com/syk25/satlas

An open-source platform that provides satellite pass and dwell information based on national territory.

---

## Goals

Provide a territorial perspective on satellite data that existing tools do not cover. Users can select a country and immediately see which satellites are passing over its airspace, along with dwell time, mission type, and operating country breakdowns.

---

## Target Users

- Space and satellite researchers, students
- Defense and security professionals
- Researchers who need to analyze satellite pass patterns over specific territories

---

## Features

**Entry**
- Select a country on an interactive 3D globe

**Default view on country selection**
- Real-time list of satellites currently passing over the selected country

**Core data perspectives**
- Dwell time quantification per satellite
- Theoretical observation footprint visualization (nadir / horizon)

**Supporting features**
- Pass count and next expected pass time
- Mission-type filtering (communications / reconnaissance / observation)
- Breakdown by operating country

**Future expansion**
- Sub-national (administrative region) granularity
- Real swath data integration

---

## Tech Stack

| Layer | Technology | Role |
|---|---|---|
| Backend | Python 3.11 + FastAPI | API server |
| | PostgreSQL | Satellite metadata, pass history, dwell time aggregation |
| | Redis | TLE caching, real-time position pub/sub, Celery broker |
| | Celery | Async task processing |
| | APScheduler | Periodic TLE ingestion |
| | SGP4 | Orbital position calculation |
| Frontend | React + Vite + TypeScript | UI framework |
| | CesiumJS | 3D globe |
| | satellite.js | Browser-side real-time orbital calculation |
| | turf.js | Point-in-polygon intersection |
| Infra | Docker Compose | Development environment |
| | Fly.io / Vercel | Production deployment (backend / frontend) |
| | Upstash | Managed Redis |
| | Cloudflare | DNS / CDN |
| DevOps | GitHub Actions | CI/CD, environment separation (dev/prod) |
| Data | CelesTrak | TLE data source |
| | Natural Earth | GeoJSON national boundary data |

For key architectural decisions, see [docs/adr/](adr/).

---

## Boundary Data Policy

Country boundaries are sourced from Natural Earth. Some territories have disputed borders or contested sovereignty. Satlas does not take a political position on any territorial dispute.

- Disputed territories are rendered with distinct visual styling (dashed borders)
- Satellite data is available for all regions without restriction
- Boundary data follows Natural Earth conventions; see [ADR-003](adr/ADR-003-disputed-territories.md) for full rationale

---

## Out of Scope

- Access to classified military data
- Commercial imagery sales
- Mobile application

---

## Operating Model

Open Source (MIT) + GitHub Sponsors
