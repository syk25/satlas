import { useEffect, useState } from 'react'

export interface CountryInfo {
  code: string
  name: string
}

type Ring = [number, number][]
type GeoFeature = {
  geometry: { type: string; coordinates: any }
  properties: Record<string, string>
}

// Ray casting point-in-polygon. GeoJSON coords are [lon, lat].
function pointInRing(lat: number, lon: number, ring: Ring): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi)
      inside = !inside
  }
  return inside
}

function pointInPolygon(lat: number, lon: number, coords: Ring[]): boolean {
  if (!pointInRing(lat, lon, coords[0])) return false
  for (let i = 1; i < coords.length; i++)
    if (pointInRing(lat, lon, coords[i])) return false // inside hole
  return true
}

function findCountry(
  lat: number,
  lon: number,
  features: GeoFeature[]
): CountryInfo | null {
  for (const f of features) {
    const code = f.properties?.ISO_A2
    if (!code || code === '-99') continue
    const name = f.properties?.NAME ?? f.properties?.ADMIN ?? ''
    const { type, coordinates } = f.geometry
    if (type === 'Polygon') {
      if (pointInPolygon(lat, lon, coordinates)) return { code, name }
    } else if (type === 'MultiPolygon') {
      for (const poly of coordinates)
        if (pointInPolygon(lat, lon, poly)) return { code, name }
    }
  }
  return null
}

// Module-level cache: fetch once, reuse across all hook instances.
let featuresCache: GeoFeature[] | null = null
let fetchPromise: Promise<GeoFeature[]> | null = null

function loadFeatures(): Promise<GeoFeature[]> {
  if (featuresCache) return Promise.resolve(featuresCache)
  if (!fetchPromise) {
    fetchPromise = fetch('/countries.geojson')
      .then((r) => r.json())
      .then((data) => {
        featuresCache = data.features
        return featuresCache!
      })
  }
  return fetchPromise
}

export function useCountryAt(
  lat: number | null,
  lon: number | null
): CountryInfo | null {
  const [country, setCountry] = useState<CountryInfo | null>(null)

  useEffect(() => {
    if (lat === null || lon === null) {
      setCountry(null)
      return
    }
    // Synchronous path after first load — avoids flicker on position updates.
    if (featuresCache) {
      setCountry(findCountry(lat, lon, featuresCache))
      return
    }
    let cancelled = false
    loadFeatures().then((features) => {
      if (!cancelled) setCountry(findCountry(lat, lon, features))
    })
    return () => {
      cancelled = true
    }
  }, [lat, lon])

  return country
}
