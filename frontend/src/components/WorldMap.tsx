import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import {
  degreesLat,
  degreesLong,
  eciToGeodetic,
  gstime,
  propagate,
  twoline2satrec,
} from 'satellite.js'
import { CATEGORY_COLOR } from '../types'
import type { SatelliteCategory, SatelliteOverhead } from '../types'

export interface WorldMapHandle {
  flyTo: (lat: number, lon: number, zoom: number) => void
}

interface Props {
  onCountrySelect: (code: string, name: string) => void
  onSatelliteSelect: (sat: SatelliteOverhead | null) => void
  onSatelliteOffMap?: (direction: 'north' | 'south' | null) => void
  selectedCode: string | null
  satellites: SatelliteOverhead[]
  selectedSat: SatelliteOverhead | null
  trackedSatellite: SatelliteOverhead | null
  activeCategory: SatelliteCategory | null
}

const SAT_CLICK_RADIUS = 8 // px

// Mobile bottom-sheet covers ~72% of viewport height when open. Map operations
// (setView/fitBounds) should aim the selection at the visible upper strip
// rather than the geometric centre, otherwise the marker the user just tapped
// hides behind the sheet they triggered.
const MOBILE_BREAKPOINT_PX = 768
const PANEL_HEIGHT_RATIO = 0.72

function isMobileViewport(): boolean {
  return typeof window !== 'undefined' && window.innerWidth <= MOBILE_BREAKPOINT_PX
}

function mobilePanelHeightPx(): number {
  return Math.floor(window.innerHeight * PANEL_HEIGHT_RATIO)
}

// Shift the target latlng downward in screen space so that after the map
// centres on it, the marker visually lands in the upper (un-covered) half.
function centerForSelection(
  map: L.Map,
  lat: number,
  lon: number,
  zoom: number
): L.LatLng {
  if (!isMobileViewport()) return L.latLng(lat, lon)
  const target = map.project(L.latLng(lat, lon), zoom)
  const shifted = target.add(L.point(0, mobilePanelHeightPx() / 2))
  return map.unproject(shifted, zoom)
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

  // Draw the track twice (original + +360 shift) so it stays visible
  // regardless of which world-copy the camera is on after antimeridian crossings.
  for (const lonShift of [0, 360, -360]) {
    ctx.beginPath()
    let penDown = false
    for (let i = 0; i < points.length; i++) {
      if (i > 0 && Math.abs(points[i][1] - points[i - 1][1]) > 180) {
        ctx.stroke()
        ctx.beginPath()
        penDown = false
      }
      const pt = map.latLngToContainerPoint([points[i][0], points[i][1] + lonShift])
      if (!penDown) {
        ctx.moveTo(pt.x, pt.y)
        penDown = true
      } else ctx.lineTo(pt.x, pt.y)
    }
    ctx.stroke()
  }
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

export const WorldMap = forwardRef<WorldMapHandle, Props>(function WorldMap(
  {
    onCountrySelect,
    onSatelliteSelect,
    onSatelliteOffMap,
    selectedCode,
    satellites,
    selectedSat,
    trackedSatellite,
    activeCategory,
  }: Props,
  ref
) {
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
  // canvas positions for click detection: norad_id → {x, y}
  const satCanvasPosRef = useRef<Map<number, { x: number; y: number }>>(new Map())
  const activeCategoryRef = useRef<SatelliteCategory | null>(null)
  const onSatelliteSelectRef = useRef(onSatelliteSelect)
  const onSatelliteOffMapRef = useRef(onSatelliteOffMap)

  // Selected mode (orbit preview, no camera follow)
  const selectedSatRef = useRef<SatelliteOverhead | null>(null)
  const selectedGroundTrackRef = useRef<Array<[number, number]>>([])

  // Tracking mode
  const trackedSatRef = useRef<SatelliteOverhead | null>(null)
  const trackedSatrecRef = useRef<ReturnType<typeof twoline2satrec> | null>(null)
  const groundTrackRef = useRef<Array<[number, number]>>([])
  const trackTrailRef = useRef<Array<[number, number]>>([])
  const trackFrameRef = useRef(0)
  const trackingJustStoppedRef = useRef(false)

  useImperativeHandle(ref, () => ({
    flyTo(lat, lon, zoom) {
      mapRef.current?.flyTo([lat, lon], zoom, { animate: true, duration: 0.8 })
    },
  }))

  // Sync mutable refs (avoid stale closures in RAF)
  useEffect(() => {
    activeCategoryRef.current = activeCategory
  }, [activeCategory])

  useEffect(() => {
    onSatelliteSelectRef.current = onSatelliteSelect
  }, [onSatelliteSelect])

  useEffect(() => {
    onSatelliteOffMapRef.current = onSatelliteOffMap
  }, [onSatelliteOffMap])

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

  // Selected mode: center map on satellite + compute ground track
  useEffect(() => {
    selectedSatRef.current = selectedSat
    if (!selectedSat) {
      selectedGroundTrackRef.current = []
      return
    }
    try {
      const satrec = twoline2satrec(selectedSat.line1.trim(), selectedSat.line2.trim())
      selectedGroundTrackRef.current = computeGroundTrack(satrec)
      const pv = propagate(satrec, new Date())
      if (pv.position && typeof pv.position !== 'boolean') {
        const gst = gstime(new Date())
        const geo = eciToGeodetic(pv.position as any, gst)
        const map = mapRef.current
        if (map) {
          const lat = degreesLat(geo.latitude)
          const lon = degreesLong(geo.longitude)
          map.setView(centerForSelection(map, lat, lon, 4), 4, { animate: true })
        }
      }
    } catch {}
  }, [selectedSat])

  // Tracking mode setup / teardown
  useEffect(() => {
    if (!trackedSatellite) {
      trackingJustStoppedRef.current = true
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

    // Reset country highlight, disable drag, center on satellite
    if (geoLayerRef.current) geoLayerRef.current.setStyle(COUNTRY_DEFAULT)
    selectedLayerRef.current = null
    mapRef.current?.dragging.disable()
    mapRef.current?.scrollWheelZoom.enable()
    try {
      const pv0 = propagate(trackedSatrecRef.current!, new Date())
      if (pv0.position && typeof pv0.position !== 'boolean') {
        const gst0 = gstime(new Date())
        const geo0 = eciToGeodetic(pv0.position as any, gst0)
        const map = mapRef.current
        if (map) {
          const lat = degreesLat(geo0.latitude)
          const lon = degreesLong(geo0.longitude)
          map.setView(centerForSelection(map, lat, lon, 4), 4, { animate: true })
        }
      }
    } catch {}

    // Refresh ground track every 60s
    const timer = window.setInterval(() => {
      const satrec = trackedSatrecRef.current
      if (satrec) groundTrackRef.current = computeGroundTrack(satrec)
    }, 60_000)

    return () => {
      clearInterval(timer)
      mapRef.current?.dragging.enable()
    }
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
      minZoom: 2,
      maxZoom: 10,
      zoomControl: true,
      maxBounds: L.latLngBounds(L.latLng(-85, -720), L.latLng(85, 720)),
      maxBoundsViscosity: 0.3,
    })

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution:
        '© <a href="https://openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 20,
    }).addTo(map)

    L.control.scale({ position: 'bottomright', imperial: false }).addTo(map)

    map.on('movestart zoomstart', () => {
      trailsRef.current.clear()
      trackTrailRef.current = []
    })

    map.on('click', (e: L.LeafletMouseEvent) => {
      if (trackedSatRef.current) return
      const { x, y } = e.containerPoint
      let nearest: SatelliteOverhead | null = null
      let minDist = SAT_CLICK_RADIUS
      satCanvasPosRef.current.forEach((pos, noradId) => {
        const d = Math.sqrt((pos.x - x) ** 2 + (pos.y - y) ** 2)
        if (d < minDist) {
          minDist = d
          nearest = satellitesRef.current.find((s) => s.norad_id === noradId) ?? null
        }
      })
      if (nearest) {
        onSatelliteSelectRef.current(nearest)
        L.DomEvent.stopPropagation(e as unknown as Event)
      }
    })

    fetch('/countries.geojson')
      .then((r) => r.json())
      .then((data) => {
        // Guard: map may have been removed if the component unmounted while fetching
        if (mapRef.current !== map) return
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

          // Boundary lines at ±180° longitude (edge of interactive area)
          const xLeft = map.latLngToContainerPoint([0, -180]).x
          const xRight = map.latLngToContainerPoint([0, 180]).x
          ctx.save()
          ctx.strokeStyle = 'rgba(255,255,255,0.18)'
          ctx.lineWidth = 1
          ctx.setLineDash([6, 6])
          if (xLeft > 0 && xLeft < canvas.width) {
            ctx.beginPath()
            ctx.moveTo(xLeft, 0)
            ctx.lineTo(xLeft, canvas.height)
            ctx.stroke()
          }
          if (xRight > 0 && xRight < canvas.width) {
            ctx.beginPath()
            ctx.moveTo(xRight, 0)
            ctx.lineTo(xRight, canvas.height)
            ctx.stroke()
          }
          ctx.restore()

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
                const color =
                  tracked.category && CATEGORY_COLOR[tracked.category]
                    ? CATEGORY_COLOR[tracked.category]
                    : '#facc15'

                // Camera follow — drag is disabled, no Leaflet conflict.
                // On mobile the bottom-sheet covers the lower half, so the
                // tracked satellite must be aimed at the visible upper strip.
                const zoomNow = map.getZoom()
                map.setView(centerForSelection(map, lat, lon, zoomNow), zoomNow, {
                  animate: false,
                  noMoveStart: true,
                } as L.ZoomPanOptions)

                // ±85° boundary lines (Web Mercator coverage limit)
                const y85N = map.latLngToContainerPoint([85, 0]).y
                const y85S = map.latLngToContainerPoint([-85, 0]).y
                ctx.save()
                ctx.setLineDash([4, 8])
                ctx.lineWidth = 1
                ctx.strokeStyle = 'rgba(255,255,255,0.15)'
                ctx.beginPath()
                ctx.moveTo(0, y85N)
                ctx.lineTo(canvas.width, y85N)
                ctx.stroke()
                ctx.beginPath()
                ctx.moveTo(0, y85S)
                ctx.lineTo(canvas.width, y85S)
                ctx.stroke()
                ctx.restore()

                // Ground track
                drawGroundTrack(ctx, map, groundTrackRef.current, color)

                const offMap = Math.abs(lat) > 85

                if (offMap) {
                  onSatelliteOffMapRef.current?.(lat > 0 ? 'north' : 'south')
                  const cx = canvas.width / 2
                  const isNorth = lat > 0
                  const cy = isNorth ? 32 : canvas.height - 32
                  ctx.fillStyle = withAlpha(color, 0.9)
                  ctx.beginPath()
                  if (isNorth) {
                    ctx.moveTo(cx, cy - 10)
                    ctx.lineTo(cx - 8, cy + 6)
                    ctx.lineTo(cx + 8, cy + 6)
                  } else {
                    ctx.moveTo(cx, cy + 10)
                    ctx.lineTo(cx - 8, cy - 6)
                    ctx.lineTo(cx + 8, cy - 6)
                  }
                  ctx.closePath()
                  ctx.fill()
                  ctx.fillStyle = withAlpha(color, 0.65)
                  ctx.font = '10px system-ui, sans-serif'
                  ctx.textAlign = 'center'
                  ctx.fillText(tracked.name, cx, isNorth ? cy + 18 : cy - 12)
                } else {
                  onSatelliteOffMapRef.current?.(null)
                  const pt = map.latLngToContainerPoint([lat, lon])

                  // Footprint
                  drawFootprint(ctx, map, pv.position as any, lat, lon, color)

                  // Trail
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
                      const p2 = map.latLngToContainerPoint(
                        trail[i] as [number, number]
                      )
                      ctx.strokeStyle = withAlpha(color, alpha)
                      ctx.lineWidth = 2
                      ctx.beginPath()
                      ctx.moveTo(p1.x, p1.y)
                      ctx.lineTo(p2.x, p2.y)
                      ctx.stroke()
                    }
                  }

                  // Direction arrow (2s velocity vector)
                  try {
                    const ahead = new Date(now.getTime() + 2000)
                    const pvAhead = propagate(trackedSatrec, ahead)
                    if (pvAhead.position && typeof pvAhead.position !== 'boolean') {
                      const gstAhead = gstime(ahead)
                      const geoAhead = eciToGeodetic(pvAhead.position as any, gstAhead)
                      const ptAhead = map.latLngToContainerPoint([
                        degreesLat(geoAhead.latitude),
                        degreesLong(geoAhead.longitude),
                      ])
                      const dx = ptAhead.x - pt.x
                      const dy = ptAhead.y - pt.y
                      const len = Math.sqrt(dx * dx + dy * dy)
                      if (len > 0.5) {
                        const nx = dx / len
                        const ny = dy / len
                        const arrowLen = 18
                        const ax = pt.x + nx * arrowLen
                        const ay = pt.y + ny * arrowLen
                        const hw = 5
                        const hl = 7
                        const px = -ny
                        const py = nx
                        ctx.beginPath()
                        ctx.moveTo(pt.x, pt.y)
                        ctx.lineTo(ax, ay)
                        ctx.strokeStyle = withAlpha(color, 0.85)
                        ctx.lineWidth = 1.5
                        ctx.setLineDash([])
                        ctx.stroke()
                        ctx.beginPath()
                        ctx.moveTo(ax + nx * hl, ay + ny * hl)
                        ctx.lineTo(ax + px * hw, ay + py * hw)
                        ctx.lineTo(ax - px * hw, ay - py * hw)
                        ctx.closePath()
                        ctx.fillStyle = withAlpha(color, 0.85)
                        ctx.fill()
                      }
                    }
                  } catch {}

                  // Satellite dot
                  ctx.shadowBlur = 14
                  ctx.shadowColor = color
                  ctx.fillStyle = color
                  ctx.beginPath()
                  ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2)
                  ctx.fill()
                  ctx.shadowBlur = 0
                }
              }
            } catch {}
          } else {
            // ── Overhead / Selected mode ────────────────────────────
            const cache = satrecCacheRef.current
            if (cache.size > 0) {
              const now = new Date()
              const trails = trailsRef.current
              const catFilter = activeCategoryRef.current
              const selSat = selectedSatRef.current
              frameRef.current++
              const addTrail = frameRef.current % TRAIL_EVERY_N_FRAMES === 0
              const newPositions = new Map<number, { x: number; y: number }>()

              cache.forEach((satrec, noradId) => {
                try {
                  const sat = satellitesRef.current.find((s) => s.norad_id === noradId)
                  // When a satellite is selected, hide all others
                  if (selSat && sat?.norad_id !== selSat.norad_id) return
                  if (!selSat && catFilter && sat?.category !== catFilter) return

                  const pv = propagate(satrec, now)
                  if (!pv.position || typeof pv.position === 'boolean') return
                  const gst = gstime(now)
                  const geo = eciToGeodetic(pv.position as any, gst)
                  const lat = degreesLat(geo.latitude)
                  const lon = degreesLong(geo.longitude)
                  const pt = map.latLngToContainerPoint([lat, lon])

                  newPositions.set(noradId, { x: pt.x, y: pt.y })

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

              satCanvasPosRef.current = newPositions

              // Draw ground track for selected satellite (orbit preview mode)
              if (selectedSatRef.current && selectedGroundTrackRef.current.length > 1) {
                const selColor = selectedSatRef.current.category
                  ? CATEGORY_COLOR[selectedSatRef.current.category]
                  : '#facc15'
                drawGroundTrack(ctx, map, selectedGroundTrackRef.current, selColor)
              }
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
        if (!trackingJustStoppedRef.current) {
          const panelPx = isMobileViewport() ? mobilePanelHeightPx() : 0
          mapRef.current?.fitBounds((lyr as L.GeoJSON).getBounds(), {
            paddingTopLeft: [60, 60],
            paddingBottomRight: [60, 60 + panelPx],
            maxZoom: 6,
          })
        }
        trackingJustStoppedRef.current = false
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
})
