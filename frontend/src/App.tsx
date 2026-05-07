import { useCallback, useState } from 'react'
import { CountryDropdown } from './components/CountryDropdown'
import { SatellitePanel } from './components/SatellitePanel'
import { WorldMap } from './components/WorldMap'
import { useOverheadSatellites } from './hooks/useOverheadSatellites'
import type { SatelliteOverhead } from './types'

export default function App() {
  const [selected, setSelected] = useState<{ code: string; name: string } | null>(null)
  const [trackedSatellite, setTrackedSatellite] = useState<SatelliteOverhead | null>(
    null
  )
  const [preTrackSelected, setPreTrackSelected] = useState<{
    code: string
    name: string
  } | null>(null)

  const { data, loading, error } = useOverheadSatellites(selected?.code ?? null)

  const handleCountrySelect = useCallback((code: string, name: string) => {
    setSelected({ code, name })
    setTrackedSatellite(null)
    setPreTrackSelected(null)
  }, [])

  const handleTrack = useCallback(
    (sat: SatelliteOverhead) => {
      setPreTrackSelected(selected)
      setTrackedSatellite(sat)
      setSelected(null)
    },
    [selected]
  )

  const handleStopTracking = useCallback(() => {
    setTrackedSatellite(null)
    setSelected(preTrackSelected)
    setPreTrackSelected(null)
  }, [preTrackSelected])

  return (
    <div className="layout">
      <div className="globe-container">
        <WorldMap
          onCountrySelect={handleCountrySelect}
          selectedCode={selected?.code ?? null}
          satellites={data ?? []}
          trackedSatellite={trackedSatellite}
        />
        {!trackedSatellite && (
          <CountryDropdown
            onSelect={handleCountrySelect}
            selectedCode={selected?.code ?? null}
          />
        )}
      </div>
      <SatellitePanel
        countryName={selected?.name ?? null}
        data={data}
        loading={loading}
        error={error}
        trackedSatellite={trackedSatellite}
        onTrack={handleTrack}
        onStopTracking={handleStopTracking}
      />
    </div>
  )
}
