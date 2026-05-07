import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef, useState } from 'react'
import {
  degreesLat,
  degreesLong,
  eciToGeodetic,
  gstime,
  propagate,
  twoline2satrec,
} from 'satellite.js'
import type { SatelliteOverhead, SatellitePosition } from '../types'

interface Props {
  onCountrySelect: (code: string, name: string) => void
  selectedCode: string | null
  satellites: SatelliteOverhead[]
  allPositions: SatellitePosition[]
}

function getSatPosition(
  line1: string,
  line2: string,
  now: Date
): [number, number] | null {
  try {
    const satrec = twoline2satrec(line1, line2)
    const pv = propagate(satrec, now)
    if (!pv.position || typeof pv.position === 'boolean') return null
    const gst = gstime(now)
    const geo = eciToGeodetic(pv.position as any, gst)
    return [degreesLat(geo.latitude), degreesLong(geo.longitude)]
  } catch {
    return null
  }
}

const COUNTRY_DEFAULT: L.PathOptions = {
  color: 'rgba(255,255,255,0.45)',
  weight: 1,
  fillColor: '#ffffff',
  fillOpacity: 0.001,
}
const COUNTRY_HOVER: L.PathOptions = { ...COUNTRY_DEFAULT, fillOpacity: 0.15 }
const COUNTRY_SELECTED: L.PathOptions = {
  ...COUNTRY_DEFAULT,
  fillColor: '#3b82f6',
  fillOpacity: 0.45,
  color: '#60a5fa',
  weight: 2,
}

export function WorldMap({
  onCountrySelect,
  selectedCode,
  satellites,
  allPositions,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const geoLayerRef = useRef<L.GeoJSON | null>(null)
  const selectedLayerRef = useRef<L.Layer | null>(null)
  const markerLayerRef = useRef<L.LayerGroup | null>(null)

  // Overhead satellite positions, refreshed every 5s via satellite.js
  const [overheadPositions, setOverheadPositions] = useState<[number, number][]>([])

  // Init map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = L.map(containerRef.current, {
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

    const markerLayer = L.layerGroup().addTo(map)
    markerLayerRef.current = markerLayer

    fetch('/countries.geojson')
      .then((r) => r.json())
      .then((data) => {
        const layer = L.geoJSON(data, {
          style: () => COUNTRY_DEFAULT,
          onEachFeature: (feature, lyr) => {
            lyr.on({
              mouseover(e) {
                const l = e.target as L.Path
                if (l !== selectedLayerRef.current) l.setStyle(COUNTRY_HOVER)
              },
              mouseout(e) {
                const l = e.target as L.Path
                if (l !== selectedLayerRef.current) l.setStyle(COUNTRY_DEFAULT)
              },
              click() {
                const code: string = feature.properties?.ISO_A2
                const name: string =
                  feature.properties?.NAME ?? feature.properties?.ADMIN ?? ''
                if (!code || code === '-99') return

                if (selectedLayerRef.current) {
                  ;(selectedLayerRef.current as L.Path).setStyle(COUNTRY_DEFAULT)
                }
                ;(lyr as L.Path).setStyle(COUNTRY_SELECTED)
                selectedLayerRef.current = lyr

                map.fitBounds((lyr as L.GeoJSON).getBounds(), {
                  padding: [40, 40],
                  maxZoom: 6,
                })

                onCountrySelect(code, name)
              },
            })
          },
        }).addTo(map)
        geoLayerRef.current = layer
      })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
      geoLayerRef.current = null
      selectedLayerRef.current = null
      markerLayerRef.current = null
    }
  }, [onCountrySelect])

  // Reset country highlight when deselected externally
  useEffect(() => {
    if (!selectedCode && selectedLayerRef.current) {
      ;(selectedLayerRef.current as L.Path).setStyle(COUNTRY_DEFAULT)
      selectedLayerRef.current = null
    }
  }, [selectedCode])

  // Recompute overhead satellite positions every 5s (only when a country is selected)
  useEffect(() => {
    if (satellites.length === 0) {
      setOverheadPositions([])
      return
    }

    const compute = () => {
      const now = new Date()
      const positions: [number, number][] = []
      satellites.forEach((sat) => {
        const pos = getSatPosition(sat.line1, sat.line2, now)
        if (pos) positions.push(pos)
      })
      setOverheadPositions(positions)
    }

    compute()
    const interval = setInterval(compute, 5000)
    return () => clearInterval(interval)
  }, [satellites])

  // Render markers: overhead when country selected, all positions otherwise
  useEffect(() => {
    const layer = markerLayerRef.current
    if (!layer) return

    layer.clearLayers()

    const toRender: [number, number][] = selectedCode
      ? overheadPositions
      : allPositions.map((p) => [p.lat, p.lon])

    toRender.forEach(([lat, lon]) => {
      L.circleMarker([lat, lon], {
        radius: 4,
        color: '#000',
        weight: 1,
        fillColor: '#facc15',
        fillOpacity: 1,
      }).addTo(layer)
    })
  }, [selectedCode, overheadPositions, allPositions])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
}
