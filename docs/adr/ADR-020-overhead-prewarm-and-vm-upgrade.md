# ADR-020: Overhead Prewarm + shared-cpu-2x VM Upgrade

**Status**: Accepted
**Date**: 2026-05-09

---

## Context

After the membership-refresh implementation (ADR-018) and the boundary fast-path (bbox + prepared geometry), a cold `/overhead/{cc}` request still took ~7 s on the production `shared-cpu-1x` machine for large countries (CN, US, RU). The frontend panel opens immediately, but the satellite list arrives 7 s later — well outside the desired "click → data" target of 1 s.

Two facts drove the decision:

1. **No algorithmic path to <1 s on the cold path.** The 30-minute simulation involves ~16k satellites × 31 samples = ~500k SGP4 calls; even with the optimizations already in place, the inherent CPU cost is several seconds on a shared 1 vCPU.
2. **The lazy cache fill from ADR-018 only helps on the second visit per country.** First-time clicks always pay the simulation cost.

Therefore the answer is operational, not algorithmic: **make the cache always warm**, then size the VM so background warming does not crowd out request handling.

---

## Decision

**1. VM upgrade: `shared-cpu-1x` → `shared-cpu-2x`.**

Doubles vCPU count for ~$3–5/month (Fly.io pricing). Memory bumps from 512 MB → keeps at 512 MB (memory is not the bottleneck; the positions cache + JSON serialization fit well under 100 MB).

**2. Background prewarm of `/overhead` for every country, every 15 minutes.**

A new APScheduler job iterates all loaded country codes and runs `simulate_overhead_window` for the default request shape (no category, `include_inactive=false`), storing the result under the same cache key the request handler reads. Every country becomes a guaranteed cache hit after the first scheduler tick.

Triggers:

- Every 15 minutes (the simulation window is 30 minutes, so 15 minutes keeps stale-data exposure to half the window — same logic as the client refresh in ADR-018).
- Once at server startup, 30 s after boot, so a fresh deploy is warm before users start clicking.
- Immediately after `warm_positions_cache` completes for the first time post-restart, so prewarm runs against the freshest positions.

`include_inactive=true` is **not** prewarmed — it's a power-user toggle with much heavier simulation cost (3× the satellites). It stays lazy.

**3. Sample interval 60 s → 90 s.**

Reduces SGP4 calls per simulation by ~33 %. Entry/exit timing accuracy goes from ±30 s to ±45 s — invisible to the user because the 1 Hz client gating interpolates within the window. ADR-018's notes already flagged 60 s as a tunable trade-off; this ADR moves the dial.

---

## Cost Analysis

### Backend CPU on shared-cpu-2x (2 vCPU)

| Workload | Cycle | Cost | CPU usage |
|---|---|---|---|
| `warm_positions_cache` (ADR-016) | 60 s | ~10 s on 2 vCPU | ~17 % |
| `visits/recompute` (ADR-019) | 12 h | ~5 min | ~0.7 % |
| **`prewarm_overhead` (this ADR)** | 15 min | ~3-4 min on 2 vCPU* | **~25 %** |
| **Total baseline** | | | **~43 %** |

*Single-threaded simulation per country, but iteration across countries can run in parallel-ish via `asyncio.to_thread` chunks. Realistic estimate based on 200 countries × ~1 s/country (PAYLOAD-only after the boundary fast-path).

This leaves ~57 % vCPU available for request handling and burst — comfortable margin on shared-cpu-2x. On shared-cpu-1x the same workload would have peaked at ~86 %, leaving no headroom.

### Monetary cost

- shared-cpu-1x → shared-cpu-2x ≈ +$3–5/month
- Within the spirit of ADR-014's "free-tier first" — the upgrade is cheap, scales the existing infrastructure rather than introducing new services, and unlocks the 1-second response target that defines a usable interactive map.

---

## Alternatives Considered

### A. dedicated-cpu-1x upgrade
Avoids shared-CPU steal time entirely. Rejected: ~$10–30/month for marginal benefit over shared-cpu-2x; the vCPU contention on shared CPUs has not been observed as a real bottleneck in current monitoring.

### B. Popular-territory-only prewarm (KR, US, CN, JP, RU, GB, FR, DE …)
Prewarm only ~20 frequently-clicked countries; the rest stay lazy.
- Pros: cheaper CPU (~7 % instead of 25 %), works on shared-cpu-1x.
- Cons: loses the absolute "1 second always" guarantee; users from less-popular countries still see 5–7 s on first click. Picking the popular set requires telemetry the project doesn't have yet.
- Rejected because the target was unconditional, not situational.

### C. Frontend two-stage rendering (instant snapshot, then full window)
Frontend gets the in-territory satellites instantly from the positions cache, then refetches the windowed result a few seconds later.
- Pros: no extra backend cost.
- Cons: significant client-side complexity, breaks the ADR-018 single-fetch model, exposes the user to a list that updates "soon" instead of being correct.
- Rejected as a UX regression dressed up as a perf win.

### D. Move prewarm to a separate worker
Run the prewarm in a Celery worker on a different machine.
- Pros: fully decouples background CPU from request handling.
- Cons: new machine ($3–5/month anyway) + Celery operational complexity for a workload the API process can absorb on a 2 vCPU machine.
- Reconsider only if shared-cpu-2x measurements show CPU pressure.

---

## Consequences

**Positive**
- Cold-path `/overhead/{cc}` for any country drops from ~7 s to <100 ms (Redis read + filter only).
- Sample-interval reduction propagates the win to the lazy `include_inactive=true` path too: 30-min sims for power users get faster.
- Headroom on the 2 vCPU machine handles burst load without queuing requests behind the scheduler.

**Negative**
- Operational cost goes from $0 → ~$5/month — first paid line item for the project.
- Steady-state CPU rises from ~17 % → ~43 %. If observability shows >70 % sustained, the prewarm needs to back off (longer interval) or move out (alternative D).
- Prewarm sweeping every country means every country's polygon gets warmed into shapely's prepared cache on the first cycle — expect a one-time ~30 s startup delay as `prep` is built for all 200 countries. Bounded.

---

## Notes

- The prewarm job lives next to `warm_positions_cache` in the scheduler. Both are CPU-heavy and benefit from running in `asyncio.to_thread`.
- Cache key shape stays the same: `satlas:overhead:{cc}` for the default case; the prewarm writes the exact same payload the request handler builds, so cache hits are bit-for-bit identical to a lazy fill.
- Cache TTL is extended from 5 minutes (ADR-018) to 20 minutes — slightly longer than the 15-minute prewarm interval so a slow scheduler tick can't leave the cache empty between cycles.
- VM size change is applied via `fly.toml` (`size = "shared-cpu-2x"`) — requires `fly deploy` to take effect; existing machines need `fly machine update --vm-size shared-cpu-2x` or replacement.
- This is the first ADR that supersedes parameters from a prior ADR — sample interval was 60 s in ADR-018, is 90 s here. Documented in both places to avoid future confusion.
