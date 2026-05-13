import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import MapHint from '../components/MapHint'
import { SatellitePanel } from '../components/SatellitePanel'
import { WorldMap } from '../components/WorldMap'
import { useOverheadSatellites } from '../hooks/useOverheadSatellites'
import { usePassSchedule } from '../hooks/usePassSchedule'
import type { PanelTab, SatelliteCategory, SatelliteOverhead } from '../types'

const GATING_TICK_MS = 1000

export default function MapPage() {
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
  const [panelTab, setPanelTab] = useState<PanelTab>('overhead')

  // Reset selection state when the Navbar brand is clicked. The navigator
  // pushes a fresh `reset` token into location.state each click, so a
  // re-click on the same `/` route still fires this effect even though the
  // path didn't change. Map zoom/pan is intentionally preserved — only
  // selection-related state goes back to its initial value.
  const location = useLocation()
  const resetToken = (location.state as { reset?: number } | null)?.reset
  useEffect(() => {
    if (resetToken === undefined) return
    setSelected(null)
    setTrackedSatellite(null)
    setPreTrackSelected(null)
    setSelectedSat(null)
    setActiveCategory(null)
    setSatOffMapDir(null)
    setIncludeInactive(false)
    setPanelTab('overhead')
  }, [resetToken])

  const { data, loading, error } = useOverheadSatellites(
    selected?.code ?? null,
    includeInactive
  )
  const passes = usePassSchedule(selected?.code ?? null)

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
      if (prev?.code !== code) {
        setActiveCategory(null)
        // Resetting the tab on country change avoids the schedule view
        // briefly showing the previous country's passes during fetch.
        setPanelTab('overhead')
      }
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
        <MapHint externalDismiss={selected !== null} />
      </div>
      <SatellitePanel
        countryName={selected?.name ?? null}
        data={data === null ? null : visibleSatellites}
        loading={loading}
        error={error}
        passes={passes.data}
        passesLoading={passes.loading}
        passesError={passes.error}
        tab={panelTab}
        onTabChange={setPanelTab}
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
  )
}
