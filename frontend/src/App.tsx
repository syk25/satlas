import { useCallback, useState } from 'react'
import { SatellitePanel } from './components/SatellitePanel'
import { WorldMap } from './components/WorldMap'
import { useOverheadSatellites } from './hooks/useOverheadSatellites'
import { useSatellitePositions } from './hooks/useSatellitePositions'

export default function App() {
  const [selected, setSelected] = useState<{ code: string; name: string } | null>(null)

  const allPositions = useSatellitePositions()
  const { data, loading, error } = useOverheadSatellites(selected?.code ?? null)

  const handleCountrySelect = useCallback((code: string, name: string) => {
    setSelected({ code, name })
  }, [])

  return (
    <div className="layout">
      <div className="globe-container">
        <WorldMap
          onCountrySelect={handleCountrySelect}
          selectedCode={selected?.code ?? null}
          satellites={data ?? []}
          allPositions={allPositions}
        />
      </div>
      <SatellitePanel
        countryName={selected?.name ?? null}
        data={data}
        loading={loading}
        error={error}
      />
    </div>
  )
}
