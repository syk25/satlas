# ADR-012: Frontend Map Library — Leaflet over CesiumJS

**Date:** 2026-05-07  
**Status:** Accepted

---

## Context

The initial frontend design called for a CesiumJS 3D globe to visualize satellite positions over national territories. CesiumJS was selected for its native 3D globe rendering and satellite tracking capabilities (e.g., CZML, satellite.js integration).

During implementation, the following issues surfaced:

1. **Ion access token required.** CesiumJS defaults to Cesium ion assets (World Imagery, World Terrain). Without a valid token the globe fails to load imagery and throws 401 errors. Managing tokens adds operational overhead.

2. **GeoJSON winding order.** CesiumJS strictly enforces RFC 7946 (exterior rings must be CCW). Natural Earth data uses CW exterior rings. This caused Cesium to fill the complement of every country polygon, rendering large filled artifacts over Russia, USA, China, and others. The fix required a one-time Shapely preprocessing step (`orient(sign=1.0)`).

3. **Circumpolar polygon failure.** Antarctica's polygon wraps the South Pole. Cesium cannot triangulate circumpolar polygons correctly regardless of winding order; the feature had to be excluded entirely.

4. **Click detection with transparent fill.** Cesium picks on rendered pixels, not on polygon area. Setting fill to `Color.TRANSPARENT` made polygon bodies unclickable — only strokes were pickable. A non-zero alpha (0.001) was required as a workaround.

5. **Bundle size.** CesiumJS adds ~50 MB to `node_modules` and requires a dedicated Vite plugin to copy static Workers and Assets into the build output.

6. **2D UX preference.** After testing, the 2D flat map proved easier to use and less error-prone than the 3D globe for the core use case of selecting a country and viewing overhead satellites.

## Decision

Replace CesiumJS with **Leaflet + react-leaflet** for the frontend map.

Country boundaries are rendered as a GeoJSON layer using the preprocessed Natural Earth 50m dataset. Satellite positions are computed client-side with satellite.js and rendered as Leaflet `CircleMarker` elements.

## Consequences

**Benefits:**
- No token or account required; OSM and CartoDB tiles are free and open.
- Country click detection works natively via Leaflet's `onEachFeature` callback — no pixel-pick workaround.
- Winding order is irrelevant to Leaflet's renderer.
- Bundle size reduced significantly (~50 MB → ~200 KB for Leaflet).
- Simpler React integration via react-leaflet.

**Trade-offs:**
- Loss of 3D globe capability. Real-time 3D orbital visualization (e.g., satellite ground tracks in 3D) is no longer possible without reintroducing a 3D library.
- Leaflet is 2D only; altitude of satellites is not representable without additional visual encoding (e.g., marker size, color).

## Alternatives Considered

- **Cesium 2D mode (`SceneMode.SCENE2D`):** Keeps CesiumJS but switches to a flat projection. Still requires the ion token and winding-order preprocessing; gains nothing over Leaflet for a 2D use case.
- **Mapbox GL JS:** More powerful than Leaflet, but requires a Mapbox token and has usage-based pricing. Not consistent with the free-tier-first constraint (ADR-004).
