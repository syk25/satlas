import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'
import {
  degreesLat,
  degreesLong,
  eciToGeodetic,
  gstime,
  propagate,
  twoline2satrec,
} from 'satellite.js'
import { CATEGORY_COLOR } from '../types'
import type { SatelliteOverhead } from '../types'

interface Props {
  onCountrySelect: (code: string, name: string) => void
  selectedCode: string | null
  satellites: SatelliteOverhead[]
  trackedSatellite: SatelliteOverhead | null
}

const COUNTRY_DEFAULT: L.PathOptions = {
  color: 'rgba(255,255,255,0.2)',
  weight: 0.5,
  fillColor: '#ffffff',
  fillOpacity: 0.01,
}
const COUNTRY_HOVER: L.PathOptions = { ...COUNTRY_DEFAULT, fillOpacity: 0.08 }
const COUNTRY_DIMMED: L.PathOptions = {
  color: 'rgba(255,255,255,0.04)',
  weight: 0.5,
  fillColor: '#000000',
  fillOpacity: 0.6,
}
const COUNTRY_FOCUSED: L.PathOptions = {
  color: '#60a5fa',
  weight: 2.5,
  fillColor: '#3b82f6',
  fillOpacity: 0.12,
}

const TRAIL_POINTS = 14
const TRAIL_EVERY_N_FRAMES = 18
const TRACK_TRAIL_POINTS = 40
const GROUND_TRACK_MINUTES = 95
const GROUND_TRACK_STEP_SEC = 30

function withAlpha(color: string, alpha: number): string {
  if (color.startsWith('#') && color.length === 7) {
    const r = parseInt(color.slice(1, 3), 16)
    const g = parseInt(color.slice(3, 5), 16)
    const b = parseInt(color.slice(5, 7), 16)
    return `rgba(${r},${g},${b},${alpha})`
  }
  return color.replace(/[\d.]+\)$/, `${alpha})`)
}

function computeGroundTrack(
  satrec: ReturnType<typeof twoline2satrec>
): Array<[number, number]> {
  const points: Array<[number, number]> = []
  const now = new Date()
  for (let t = 0; t <= GROUND_TRACK_MINUTES * 60; t += GROUND_TRACK_STEP_SEC) {
    const time = new Date(now.getTime() + t * 1000)
    try {
      const pv = propagate(satrec, time)
      if (!pv.position || typeof pv.position === 'boolean') continue
      const gst = gstime(time)
      const geo = eciToGeodetic(pv.position as any, gst)
      points.push([degreesLat(geo.latitude), degreesLong(geo.longitude)])
    } catch {
      /* skip bad propagation */
    }
  }
  return points
}

function drawGroundTrack(
  ctx: CanvasRenderingContext2D,
  map: L.Map,
  points: Array<[number, number]>,
  color: string
) {
  if (points.length < 2) return
  ctx.setLineDash([6, 5])
  ctx.lineWidth = 1.5
  ctx.strokeStyle = withAlpha(color, 0.45)
  ctx.beginPath()
  let started = false
  for (let i = 0; i < points.length; i++) {
    if (i > 0 && Math.abs(points[i][1] - points[i - 1][1]) > 180) {
      ctx.stroke()
      ctx.beginPath()
      started = false
    }
    const pt = map.latLngToContainerPoint(points[i] as [number, number])
    if (!started) {
      ctx.moveTo(pt.x, pt.y)
      started = true
    } else {
      ctx.lineTo(pt.x, pt.y)
    }
  }
  ctx.stroke()
  ctx.setLineDash([])
}

function drawFootprint(
  ctx: CanvasRenderingContext2D,
  map: L.Map,
  eci: { x: number; y: number; z: number },
  lat: number,
  lon: number,
  color: string
) {
  const r = Math.sqrt(eci.x ** 2 + eci.y ** 2 + eci.z ** 2)
  const rhoRad = Math.acos(Math.min(6371 / r, 1))
  const rhoDeg = (rhoRad * 180) / Math.PI

  const center = map.latLngToContainerPoint([lat, lon])
  const edgeLat = Math.max(-89, Math.min(89, lat + rhoDeg))
  const edge = map.latLngToContainerPoint([edgeLat, lon])
  const radius = Math.abs(edge.y - center.y)
  if (radius < 4) return

  const grad = ctx.createRadialGradient(
    center.x,
    center.y,
    0,
    center.x,
    center.y,
    radius
  )
  grad.addColorStop(0, withAlpha(color, 0.18))
  grad.addColorStop(0.5, withAlpha(color, 0.07))
  grad.addColorStop(1, withAlpha(color, 0))
  ctx.fillStyle = grad
  ctx.beginPath()
  ctx.arc(center.x, center.y, radius, 0, Math.PI * 2)
  ctx.fill()
}

export function WorldMap({
  onCountrySelect,
  selectedCode,
  satellites,
  trackedSatellite,
}: Props) {
  const mapDivRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const geoLayerRef = useRef<L.GeoJSON | null>(null)
  const selectedLayerRef = useRef<L.Layer | null>(null)
  const animRef = useRef<number>(0)
  const frameRef = useRef(0)

  // Overhead mode
  const satrecCacheRef = useRef<Map<number, ReturnType<typeof twoline2satrec>>>(
    new Map()
  )
  const trailsRef = useRef<Map<number, Array<[number, number]>>>(new Map())
  const satellitesRef = useRef<SatelliteOverhead[]>([])

  // Tracking mode
  const trackedSatRef = useRef<SatelliteOverhead | null>(null)
  const trackedSatrecRef = useRef<ReturnType<typeof twoline2satrec> | null>(null)
  const groundTrackRef = useRef<Array<[number, number]>>([])
  const trackTrailRef = useRef<Array<[number, number]>>([])
  const trackFrameRef = useRef(0)

  // Sync overhead satellites
  useEffect(() => {
    satellitesRef.current = satellites
    satrecCacheRef.current.clear()
    trailsRef.current.clear()
    frameRef.current = 0
    satellites.forEach((sat) => {
      try {
        satrecCacheRef.current.set(
          sat.norad_id,
          twoline2satrec(sat.line1.trim(), sat.line2.trim())
        )
      } catch {}
    })
  }, [satellites])

  // Tracking mode setup / teardown
  useEffect(() => {
    if (!trackedSatellite) {
      trackedSatRef.current = null
      trackedSatrecRef.current = null
      groundTrackRef.current = []
      trackTrailRef.current = []
      trackFrameRef.current = 0
      return
    }

    trackedSatRef.current = trackedSatellite
    try {
      const satrec = twoline2satrec(
        trackedSatellite.line1.trim(),
        trackedSatellite.line2.trim()
      )
      trackedSatrecRef.current = satrec
      groundTrackRef.current = computeGroundTrack(satrec)
      trackTrailRef.current = []
      trackFrameRef.current = 0
    } catch {
      return
    }

    // Reset country highlight and zoom out to world view
    if (geoLayerRef.current) geoLayerRef.current.setStyle(COUNTRY_DEFAULT)
    selectedLayerRef.current = null
    mapRef.current?.setView([20, 0], 2, { animate: true })

    // Refresh ground track every 60s (orbit shifts ~0.25°/s)
    const timer = window.setInterval(() => {
      const satrec = trackedSatrecRef.current
      if (satrec) groundTrackRef.current = computeGroundTrack(satrec)
    }, 60_000)

    return () => clearInterval(timer)
  }, [trackedSatellite])

  // Canvas resize
  useEffect(() => {
    const canvas = canvasRef.current
    const mapDiv = mapDivRef.current
    if (!canvas || !mapDiv) return
    const sync = () => {
      canvas.width = mapDiv.clientWidth
      canvas.height = mapDiv.clientHeight
    }
    sync()
    const ro = new ResizeObserver(sync)
    ro.observe(mapDiv)
    return () => ro.disconnect()
  }, [])

  // Map init + RAF loop
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return

    const map = L.map(mapDivRef.current, {
      center: [20, 0],
      zoom: 2,
      minZoom: 1,
      maxZoom: 10,
      zoomControl: true,
    })

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution:
        '© <a href="https://openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 20,
    }).addTo(map)

    map.on('movestart zoomstart', () => {
      trailsRef.current.clear()
      trackTrailRef.current = []
    })

    fetch('/countries.geojson')
      .then((r) => r.json())
      .then((data) => {
        const layer = L.geoJSON(data, {
          style: () => COUNTRY_DEFAULT,
          onEachFeature: (feature, lyr) => {
            lyr.on({
              mouseover(e) {
                const l = e.target as L.Path
                if (l !== selectedLayerRef.current)
                  l.setStyle(selectedLayerRef.current ? COUNTRY_DIMMED : COUNTRY_HOVER)
              },
              mouseout(e) {
                const l = e.target as L.Path
                if (l !== selectedLayerRef.current)
                  l.setStyle(
                    selectedLayerRef.current ? COUNTRY_DIMMED : COUNTRY_DEFAULT
                  )
              },
              click() {
                if (trackedSatRef.current) return // ignore clicks while tracking
                const code: string = feature.properties?.ISO_A2
                const name: string =
                  feature.properties?.NAME ?? feature.properties?.ADMIN ?? ''
                if (!code || code === '-99') return
                onCountrySelect(code, name)
              },
            })
          },
        }).addTo(map)
        geoLayerRef.current = layer
      })

    mapRef.current = map

    // RAF loop
    const canvas = canvasRef.current
    const draw = () => {
      if (canvas) {
        const ctx = canvas.getContext('2d')
        if (ctx) {
          ctx.clearRect(0, 0, canvas.width, canvas.height)

          const tracked = trackedSatRef.current
          const trackedSatrec = trackedSatrecRef.current

          if (tracked && trackedSatrec) {
            // ── Tracking mode ──────────────────────────────────────
            const now = new Date()
            try {
              const pv = propagate(trackedSatrec, now)
              if (pv.position && typeof pv.position !== 'boolean') {
                const gst = gstime(now)
                const geo = eciToGeodetic(pv.position as any, gst)
                const lat = degreesLat(geo.latitude)
                const lon = degreesLong(geo.longitude)
                const pt = map.latLngToContainerPoint([lat, lon])
                const color =
                  tracked.category && CATEGORY_COLOR[tracked.category]
                    ? CATEGORY_COLOR[tracked.category]
                    : '#facc15'

                // Footprint
                drawFootprint(ctx, map, pv.position as any, lat, lon, color)

                // Ground track
                drawGroundTrack(ctx, map, groundTrackRef.current, color)

                // Trail (past positions, stored in lat/lon)
                trackFrameRef.current++
                if (trackFrameRef.current % TRAIL_EVERY_N_FRAMES === 0) {
                  trackTrailRef.current.push([lat, lon])
                  if (trackTrailRef.current.length > TRACK_TRAIL_POINTS)
                    trackTrailRef.current.shift()
                }
                const trail = trackTrailRef.current
                if (trail.length > 1) {
                  ctx.setLineDash([])
                  for (let i = 1; i < trail.length; i++) {
                    const alpha = (i / trail.length) * 0.7
                    const p1 = map.latLngToContainerPoint(
                      trail[i - 1] as [number, number]
                    )
                    const p2 = map.latLngToContainerPoint(trail[i] as [number, number])
                    ctx.strokeStyle = withAlpha(color, alpha)
                    ctx.lineWidth = 2
                    ctx.beginPath()
                    ctx.moveTo(p1.x, p1.y)
                    ctx.lineTo(p2.x, p2.y)
                    ctx.stroke()
                  }
                }

                // Satellite dot
                ctx.shadowBlur = 14
                ctx.shadowColor = color
                ctx.fillStyle = color
                ctx.beginPath()
                ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2)
                ctx.fill()
                ctx.shadowBlur = 0
              }
            } catch {}
          } else {
            // ── Overhead mode ──────────────────────────────────────
            const cache = satrecCacheRef.current
            if (cache.size > 0) {
              const now = new Date()
              const trails = trailsRef.current
              frameRef.current++
              const addTrail = frameRef.current % TRAIL_EVERY_N_FRAMES === 0

              cache.forEach((satrec, noradId) => {
                try {
                  const pv = propagate(satrec, now)
                  if (!pv.position || typeof pv.position === 'boolean') return
                  const gst = gstime(now)
                  const geo = eciToGeodetic(pv.position as any, gst)
                  const lat = degreesLat(geo.latitude)
                  const lon = degreesLong(geo.longitude)
                  const pt = map.latLngToContainerPoint([lat, lon])

                  const sat = satellitesRef.current.find((s) => s.norad_id === noradId)
                  const color =
                    sat?.category && CATEGORY_COLOR[sat.category]
                      ? CATEGORY_COLOR[sat.category]
                      : CATEGORY_COLOR['OTHER']

                  if (addTrail) {
                    const trail = trails.get(noradId) ?? []
                    trail.push([lat, lon])
                    if (trail.length > TRAIL_POINTS) trail.shift()
                    trails.set(noradId, trail)
                  }

                  const trail = trails.get(noradId)
                  if (trail && trail.length > 1) {
                    for (let i = 1; i < trail.length; i++) {
                      const alpha = (i / trail.length) * 0.5
                      const p1 = map.latLngToContainerPoint(
                        trail[i - 1] as [number, number]
                      )
                      const p2 = map.latLngToContainerPoint(
                        trail[i] as [number, number]
                      )
                      ctx.strokeStyle = withAlpha(color, alpha)
                      ctx.lineWidth = 1.5
                      ctx.beginPath()
                      ctx.moveTo(p1.x, p1.y)
                      ctx.lineTo(p2.x, p2.y)
                      ctx.stroke()
                    }
                  }

                  ctx.shadowBlur = 10
                  ctx.shadowColor = color
                  ctx.fillStyle = color
                  ctx.beginPath()
                  ctx.arc(pt.x, pt.y, 2.5, 0, Math.PI * 2)
                  ctx.fill()
                  ctx.shadowBlur = 0
                } catch {}
              })
            }
          }
        }
      }
      animRef.current = requestAnimationFrame(draw)
    }
    draw()

    return () => {
      cancelAnimationFrame(animRef.current)
      map.remove()
      mapRef.current = null
      geoLayerRef.current = null
      selectedLayerRef.current = null
    }
  }, [onCountrySelect])

  // Country highlight / dim
  useEffect(() => {
    const layer = geoLayerRef.current
    if (!layer) return
    if (!selectedCode) {
      layer.setStyle(COUNTRY_DEFAULT)
      selectedLayerRef.current = null
      return
    }
    layer.eachLayer((lyr) => {
      const code: string = (lyr as any).feature?.properties?.ISO_A2
      if (code === selectedCode) {
        ;(lyr as L.Path).setStyle(COUNTRY_FOCUSED)
        selectedLayerRef.current = lyr
        mapRef.current?.fitBounds((lyr as L.GeoJSON).getBounds(), {
          padding: [60, 60],
          maxZoom: 6,
        })
      } else {
        ;(lyr as L.Path).setStyle(COUNTRY_DIMMED)
      }
    })
  }, [selectedCode])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={mapDivRef} style={{ width: '100%', height: '100%' }} />
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          pointerEvents: 'none',
          zIndex: 650,
        }}
      />
    </div>
  )
}
