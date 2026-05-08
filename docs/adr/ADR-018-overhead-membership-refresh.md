# ADR-018: Overhead Membership Refresh — Server-Window Prediction + Client-Side Gating

**Status**: Accepted
**Date**: 2026-05-09

---

## Context

`/satellites/overhead/{country_code}` returns the satellites currently over a country at request time. The frontend fetches this list once on territory selection, then advances each satellite's position every second via `satellite.js` using the returned TLE strings. This produces correct **position** animation but a frozen **membership** set:

- Satellites that drift out of the country footprint stay rendered.
- Satellites that drift into the country footprint never appear.

The drift becomes visible within a few minutes of selecting a territory because LEO satellites cross most countries in 5–15 minutes.

ADR-005 placed real-time computation on the browser to keep the server stateless and TLE-only. That principle was applied to position, but membership re-evaluation was never specified.

A separate but related concern: the prior conversation surfaced that **visit frequency** (passes per unit time) is the meaningful sort dimension for "observation opportunity," and computing it requires the same forward-simulation infrastructure as solving the membership problem. This ADR scopes **only** the membership fix; the frequency feature builds on the same primitive but is its own ADR.

---

## Decision

**1. Server returns a 30-minute prediction window, not just a snapshot.**

`/satellites/overhead/{country_code}` returns satellites that are over the territory **now or within the next 30 minutes**, each annotated with its `entry_time` (UTC) and `exit_time` (UTC) for the current/upcoming pass.

For a satellite already over the territory at request time:
- `entry_time` is the most recent past entry (within the window).
- `exit_time` is the predicted exit.

For a satellite not yet over the territory but predicted to enter within 30 minutes:
- `entry_time` is the predicted future entry.
- `exit_time` is the predicted exit (may be after the 30-minute window — the pass continues until the satellite leaves the footprint).

**2. Client gates rendering by `now ∈ [entry_time, exit_time]`.**

Each animation tick, the frontend filters the held list by the current time. Satellites outside their entry/exit window are hidden. Satellites whose entry has arrived are shown.

**3. Client refreshes every 15 minutes.**

Half the window length. Guarantees no coverage gap: a satellite predicted at minute 29 of the previous fetch is still in the new fetch.

**4. Server-side simulation is per-country, lazy, cached.**

Simulation is triggered by the first request for a given country and cached in Redis (5-minute TTL) keyed by `(country_code, include_inactive, category)`. Sample interval: 60 seconds over a `[now, now + 30min]` range. For each satellite, transitions from "outside" to "inside" mark `entry_time`; transitions from "inside" to "outside" mark `exit_time`.

To keep cost bounded:
- Pre-filter candidates by orbital geometry: skip satellites whose footprint cannot reach the territory's latitude band given their inclination and altitude. (Quick analytical check before SGP4 sampling.)
- Reuse the existing `POSITIONS_ALL_CACHE_KEY` snapshot as the t=0 frame; only sample t = +1min … +30min via SGP4 for the surviving candidates.

---

## Alternatives Considered

### A. Periodic `/overhead` polling without prediction
Refresh the snapshot every 30–60 seconds; let the membership pop in/out at refresh boundaries.

Rejected: visible flicker on every refresh; load scales linearly with active sessions; poor fit for the smooth-animation UX already established by `satellite.js` position interpolation.

### B. Full client-side computation (load all 16k TLEs to the browser)
Browser holds the entire active catalog; computes membership against the territory polygon every tick.

Rejected: 16k TLEs is a few MB transfer per session; per-tick polygon-intersection on 16k satellites is too heavy on mobile (battery and frame budget); ADR-005's "browser-side realtime" principle does not require sending the entire dataset.

### C. Push-based updates (SSE / WebSocket)
Server pushes membership changes as they happen.

Rejected for now: adds infrastructure complexity (long-lived connections, scaling, reconnection) for a problem solvable by 15-minute polling. Reconsider if visit-frequency or pass-history features need lower latency.

### D. Longer window (60 minutes), longer refresh interval (30 minutes)
Half the request rate, double the payload.

Rejected: 30-minute window already covers most of an LEO orbital period (~90 min), capturing the next pass for most satellites. Going longer increases per-request payload without proportional UX benefit. 15-minute refresh keeps the network cadence aligned with how often a user may revisit the panel.

---

## Consequences

**Positive**
- Membership tracks orbital motion: satellites flow in and out of the country in real time.
- Same simulation infrastructure (per-country forward window) is the foundation for visit-frequency sorting (next ADR).
- No new client dependencies; uses existing TLE animation.
- Per-country caching scales by territory popularity, not session count.

**Negative**
- One extra layer of SGP4 propagation per country per 5-minute cache cycle. Bounded by candidate pre-filtering, but adds CPU vs the current pure snapshot.
- Response payload grows: a populous territory may include ~30 in-window satellites instead of the ~10 currently overhead.
- Entry/exit times depend on TLE accuracy; satellites near the footprint boundary may flicker if TLE drift is significant. Acceptable for a 30-minute horizon.
- 15-minute refresh increases request count vs the current "fetch once" pattern. Mitigated by the per-country Redis cache.

---

## Notes

- Default sort remains "currently overhead first, then by entry time." Visit-frequency sort is a separate ADR and depends on a 24h window variant of this same simulation primitive.
- The prior `entry_time` field already exists on the response model but was being filled with `now` for all rows — this ADR gives it real meaning.
- Satellites tracked individually (`/track` flow) bypass this membership logic; tracking shows a single satellite regardless of country footprint.
- Sample interval (60s) is a tradeoff: finer (10s) catches brief grazing passes that would be missed but multiplies SGP4 cost 6×. 60s is acceptable because the rendering tick (1Hz) interpolates within the entry/exit window.
