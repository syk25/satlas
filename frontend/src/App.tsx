import { useCallback, useState } from 'react'
import { Navbar } from './components/Navbar'
import { SatellitePanel } from './components/SatellitePanel'
import { WorldMap } from './components/WorldMap'
import { useOverheadSatellites } from './hooks/useOverheadSatellites'
import type { SatelliteCategory, SatelliteOverhead } from './types'

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

  const { data, loading, error } = useOverheadSatellites(selected?.code ?? null)

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
            satellites={data ?? []}
            trackedSatellite={trackedSatellite}
            activeCategory={activeCategory}
          />
        </div>
        <SatellitePanel
          countryName={selected?.name ?? null}
          data={data}
          loading={loading}
          error={error}
          trackedSatellite={trackedSatellite}
          selectedSat={selectedSat}
          activeCategory={activeCategory}
          satOffMapDir={satOffMapDir}
          onTrack={handleTrack}
          onStopTracking={handleStopTracking}
          onSelectSat={handleSelectSat}
          onCategoryChange={setActiveCategory}
        />
      </div>
    </div>
  )
}
