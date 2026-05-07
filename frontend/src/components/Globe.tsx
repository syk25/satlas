import {
  Color,
  ColorMaterialProperty,
  GeoJsonDataSource,
  Ion,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  Viewer,
  defined,
} from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { useEffect, useRef } from 'react'

Ion.defaultAccessToken = import.meta.env.VITE_CESIUM_ION_TOKEN ?? ''

const DEFAULT_FILL = new ColorMaterialProperty(
  Color.fromCssColorString('#1e3a5f').withAlpha(0.35)
)
const HOVER_FILL = new ColorMaterialProperty(
  Color.fromCssColorString('#2563eb').withAlpha(0.55)
)
const SELECTED_FILL = new ColorMaterialProperty(
  Color.fromCssColorString('#3b82f6').withAlpha(0.7)
)

interface Props {
  onCountrySelect: (code: string, name: string) => void
  selectedCode: string | null
}

export function Globe({ onCountrySelect, selectedCode }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<Viewer | null>(null)
  const hoveredRef = useRef<any>(null)
  const selectedRef = useRef<any>(null)

  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return

    const viewer = new Viewer(containerRef.current, {
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      baseLayerPicker: false,
      navigationHelpButton: false,
      animation: false,
      timeline: false,
      fullscreenButton: false,
      vrButton: false,
    })
    viewerRef.current = viewer

    GeoJsonDataSource.load('/countries.geojson', {
      stroke: Color.WHITE.withAlpha(0.25),
      fill: Color.fromCssColorString('#1e3a5f').withAlpha(0.35),
      strokeWidth: 1,
      clampToGround: true,
    }).then((ds) => viewer.dataSources.add(ds))

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

      onCountrySelect(code, name)
    }, ScreenSpaceEventType.LEFT_CLICK)

    return () => {
      handler.destroy()
      viewer.destroy()
      viewerRef.current = null
    }
  }, [onCountrySelect])

  // Reset highlight when selected country cleared externally
  useEffect(() => {
    if (!selectedCode && selectedRef.current) {
      selectedRef.current.polygon.material = DEFAULT_FILL
      selectedRef.current = null
    }
  }, [selectedCode])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
}
