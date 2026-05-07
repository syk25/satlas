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
const TRAIL_EVERY_N_FRAMES = 18 // ~3s at 60fps, captures orbital arc without crowding

export function WorldMap({ onCountrySelect, selectedCode, satellites }: Props) {
  const mapDivRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const geoLayerRef = useRef<L.GeoJSON | null>(null)
  const selectedLayerRef = useRef<L.Layer | null>(null)
  const animRef = useRef<number>(0)
  const frameRef = useRef(0)
  const satrecCacheRef = useRef<Map<number, ReturnType<typeof twoline2satrec>>>(
    new Map()
  )
  const trailsRef = useRef<Map<number, Array<[number, number]>>>(new Map())
  const satellitesRef = useRef<SatelliteOverhead[]>([])

  // Sync satellites → satrec cache (parsing TLE is expensive, do it once per change)
  useEffect(() => {
    satellitesRef.current = satellites
    const cache = satrecCacheRef.current
    cache.clear()
    trailsRef.current.clear()
    frameRef.current = 0
    satellites.forEach((sat) => {
      try {
        cache.set(sat.norad_id, twoline2satrec(sat.line1.trim(), sat.line2.trim()))
      } catch {}
    })
  }, [satellites])

  // Canvas resize: CSS sets layout, we set pixel dimensions
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

  // Map init + RAF animation loop
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

    // Pixel positions shift on pan/zoom — restart trails
    map.on('movestart zoomstart', () => trailsRef.current.clear())

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

    // RAF loop — runs continuously, reads refs so no stale closure
    const canvas = canvasRef.current
    const draw = () => {
      if (canvas) {
        const ctx = canvas.getContext('2d')
        if (ctx) {
          ctx.clearRect(0, 0, canvas.width, canvas.height)

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

                // Accumulate trail in lat/lon (pixel-independent)
                if (addTrail) {
                  const trail = trails.get(noradId) ?? []
                  trail.push([lat, lon])
                  if (trail.length > TRAIL_POINTS) trail.shift()
                  trails.set(noradId, trail)
                }

                // Resolve color once per satellite
                const sat = satellitesRef.current.find((s) => s.norad_id === noradId)
                const color =
                  sat?.category && CATEGORY_COLOR[sat.category]
                    ? CATEGORY_COLOR[sat.category]
                    : CATEGORY_COLOR['OTHER']

                // Draw trail
                const trail = trails.get(noradId)
                if (trail && trail.length > 1) {
                  for (let i = 1; i < trail.length; i++) {
                    const alpha = (i / trail.length) * 0.5
                    const p1 = map.latLngToContainerPoint(
                      trail[i - 1] as [number, number]
                    )
                    const p2 = map.latLngToContainerPoint(trail[i] as [number, number])
                    ctx.strokeStyle = color.startsWith('rgba')
                      ? color.replace(/[\d.]+\)$/, `${alpha})`)
                      : `${color}${Math.round(alpha * 255)
                          .toString(16)
                          .padStart(2, '0')}`
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
