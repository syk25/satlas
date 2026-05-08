import { useCallback, useEffect, useRef, useState } from 'react'
import { Navbar } from './components/Navbar'
import { SatellitePanel } from './components/SatellitePanel'
import { WorldMap } from './components/WorldMap'
import { useOverheadSatellites } from './hooks/useOverheadSatellites'
import type { SatelliteCategory, SatelliteOverhead } from './types'

const GATING_TICK_MS = 1000

export default function App() {
  const [selected, setSelected] = useState<{ code: string; name: string } | null>(null)
  const [trackedSatellite, setTrackedSatellite] = useState<SatelliteOverhead | null>(
    null
  )
  const [preTrackSelected, setPreTrackSelected] = useState<{
    code: string
    name: string
  } | null>(null)
  const [selectedSat, setSelectedSat] = useState<SatelliteOverhead | null>(null)
  const [activeCategory, setActiveCategory] = useState<SatelliteCategory | null>(null)
  const [satOffMapDir, setSatOffMapDir] = useState<'north' | 'south' | null>(null)
  const [includeInactive, setIncludeInactive] = useState(false)

  const { data, loading, error } = useOverheadSatellites(
    selected?.code ?? null,
    includeInactive
  )

  // ADR-018 client-side gating: from the 30-min server window, show only
  // satellites whose [entry_time, exit_time] currently contains `now`.
  // Re-evaluate every second; only call setState when membership changes
  // to avoid redundant re-renders of the map.
  const [visibleSatellites, setVisibleSatellites] = useState<SatelliteOverhead[]>([])
  const visibleRef = useRef<SatelliteOverhead[]>([])

  useEffect(() => {
    if (!data) {
      visibleRef.current = []
      setVisibleSatellites([])
      return
    }
    const evaluate = () => {
      const now = Date.now()
      const next = data.filter((s) => {
        const entry = Date.parse(s.entry_time)
        const exit = Date.parse(s.exit_time)
        return entry <= now && now <= exit
      })
      const prev = visibleRef.current
      const changed =
        prev.length !== next.length ||
        next.some((s, i) => s.norad_id !== prev[i]?.norad_id)
      if (changed) {
        visibleRef.current = next
        setVisibleSatellites(next)
      }
    }
    evaluate()
    const tick = window.setInterval(evaluate, GATING_TICK_MS)
    return () => window.clearInterval(tick)
  }, [data])

  const handleCountrySelect = useCallback((code: string, name: string) => {
    setSelected((prev) => {
      if (prev?.code !== code) setActiveCategory(null)
      return { code, name }
    })
    setTrackedSatellite(null)
    setPreTrackSelected(null)
    setSelectedSat(null)
  }, [])

  const handleTrack = useCallback(
    (sat: SatelliteOverhead) => {
      setPreTrackSelected(selected)
      setTrackedSatellite(sat)
      setSelected(null)
      setSelectedSat(null)
    },
    [selected]
  )

  const handleStopTracking = useCallback(() => {
    setTrackedSatellite(null)
    setSelected(preTrackSelected)
    setPreTrackSelected(null)
  }, [preTrackSelected])

  const handleSelectSat = useCallback((sat: SatelliteOverhead | null) => {
    setSelectedSat(sat)
  }, [])

  return (
    <div className="layout">
      <Navbar />
      <div className="content">
        <div className="globe-container">
          <WorldMap
            onCountrySelect={handleCountrySelect}
            onSatelliteSelect={handleSelectSat}
            onSatelliteOffMap={setSatOffMapDir}
            selectedSat={selectedSat}
            selectedCode={selected?.code ?? null}
            satellites={visibleSatellites}
            trackedSatellite={trackedSatellite}
            activeCategory={activeCategory}
          />
        </div>
        <SatellitePanel
          countryName={selected?.name ?? null}
          data={data === null ? null : visibleSatellites}
          loading={loading}
          error={error}
          trackedSatellite={trackedSatellite}
          selectedSat={selectedSat}
          activeCategory={activeCategory}
          satOffMapDir={satOffMapDir}
          includeInactive={includeInactive}
          onTrack={handleTrack}
          onStopTracking={handleStopTracking}
          onSelectSat={handleSelectSat}
          onCategoryChange={setActiveCategory}
          onIncludeInactiveChange={setIncludeInactive}
        />
      </div>
    </div>
  )
}
