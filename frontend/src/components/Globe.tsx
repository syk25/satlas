import {
  Cartesian3,
  Color,
  ColorMaterialProperty,
  EllipsoidTerrainProvider,
  GeoJsonDataSource,
  ImageryLayer,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  UrlTemplateImageryProvider,
  Viewer,
  defined,
} from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import {
  degreesLat,
  degreesLong,
  eciToGeodetic,
  gstime,
  propagate,
  twoline2satrec,
} from 'satellite.js'
import { useEffect, useRef } from 'react'
import type { SatelliteOverhead } from '../types'

const OSM_LAYER = new ImageryLayer(
  new UrlTemplateImageryProvider({
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    credit: '© OpenStreetMap contributors',
  })
)

const DEFAULT_FILL = new ColorMaterialProperty(Color.fromAlpha(Color.WHITE, 0.001))
const HOVER_FILL = new ColorMaterialProperty(
  Color.fromCssColorString('#3b82f6').withAlpha(0.35)
)
const SELECTED_FILL = new ColorMaterialProperty(
  Color.fromCssColorString('#3b82f6').withAlpha(0.6)
)

interface Props {
  onCountrySelect: (code: string, name: string) => void
  selectedCode: string | null
  satellites: SatelliteOverhead[]
}

function getSatPosition(
  line1: string,
  line2: string,
  now: Date
): [number, number, number] | null {
  try {
    const satrec = twoline2satrec(line1, line2)
    const pv = propagate(satrec, now)
    if (!pv.position || typeof pv.position === 'boolean') return null
    const gst = gstime(now)
    const geo = eciToGeodetic(pv.position as any, gst)
    return [degreesLat(geo.latitude), degreesLong(geo.longitude), geo.height]
  } catch {
    return null
  }
}

export function Globe({ onCountrySelect, selectedCode, satellites }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<Viewer | null>(null)
  const hoveredRef = useRef<any>(null)
  const selectedRef = useRef<any>(null)
  const satEntitiesRef = useRef<any[]>([])

  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return

    const viewer = new Viewer(containerRef.current, {
      baseLayer: OSM_LAYER,
      terrainProvider: new EllipsoidTerrainProvider(),
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      baseLayerPicker: false,
      navigationHelpButton: false,
      animation: false,
      timeline: false,
      fullscreenButton: false,
      vrButton: false,
      infoBox: false,
      selectionIndicator: false,
    })
    viewerRef.current = viewer

    GeoJsonDataSource.load('/countries.geojson', {
      stroke: Color.WHITE.withAlpha(0.4),
      fill: Color.fromAlpha(Color.WHITE, 0.001),
      strokeWidth: 1,
    }).then((ds) => {
      if (viewer.isDestroyed()) return
      viewer.dataSources.add(ds)
    })

    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas)

    handler.setInputAction((e: { endPosition: any }) => {
      const picked = viewer.scene.pick(e.endPosition)
      const entity = defined(picked) ? picked.id : null

      if (hoveredRef.current && hoveredRef.current !== selectedRef.current) {
        hoveredRef.current.polygon.material = DEFAULT_FILL
      }

      if (entity?.polygon && entity !== selectedRef.current) {
        entity.polygon.material = HOVER_FILL
        hoveredRef.current = entity
      }
    }, ScreenSpaceEventType.MOUSE_MOVE)

    handler.setInputAction((e: { position: any }) => {
      const picked = viewer.scene.pick(e.position)
      if (!defined(picked) || !picked.id?.polygon) return

      const entity = picked.id
      const props = entity.properties
      const code: string = props?.ISO_A2?.getValue()
      const name: string = props?.NAME?.getValue() ?? props?.ADMIN?.getValue() ?? ''

      if (!code || code === '-99') return

      if (selectedRef.current) {
        selectedRef.current.polygon.material = DEFAULT_FILL
      }

      entity.polygon.material = SELECTED_FILL
      selectedRef.current = entity
      hoveredRef.current = entity

      viewer.flyTo(entity, { duration: 1.5 })
      onCountrySelect(code, name)
    }, ScreenSpaceEventType.LEFT_CLICK)

    return () => {
      handler.destroy()
      viewer.destroy()
      viewerRef.current = null
    }
  }, [onCountrySelect])

  // Reset highlight when country is deselected externally
  useEffect(() => {
    if (!selectedCode && selectedRef.current) {
      selectedRef.current.polygon.material = DEFAULT_FILL
      selectedRef.current = null
    }
  }, [selectedCode])

  // Render and refresh satellite markers every 5 seconds
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed()) return

    const clearMarkers = () => {
      satEntitiesRef.current.forEach((e) => viewer.entities.remove(e))
      satEntitiesRef.current = []
    }

    if (satellites.length === 0) {
      clearMarkers()
      return
    }

    const placeMarkers = () => {
      if (viewer.isDestroyed()) return
      clearMarkers()
      const now = new Date()
      satellites.forEach((sat) => {
        const pos = getSatPosition(sat.line1, sat.line2, now)
        if (!pos) return
        const [lat, lon, altKm] = pos
        const entity = viewer.entities.add({
          position: Cartesian3.fromDegrees(lon, lat, altKm * 1000),
          point: {
            pixelSize: 7,
            color: Color.YELLOW,
            outlineColor: Color.BLACK,
            outlineWidth: 1,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        })
        satEntitiesRef.current.push(entity)
      })
    }

    placeMarkers()
    const interval = setInterval(placeMarkers, 5000)

    return () => {
      clearInterval(interval)
      clearMarkers()
    }
  }, [satellites])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
}
