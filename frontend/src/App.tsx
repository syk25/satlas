import { useCallback, useState } from 'react'
import { CountryDropdown } from './components/CountryDropdown'
import { SatellitePanel } from './components/SatellitePanel'
import { WorldMap } from './components/WorldMap'
import { useOverheadSatellites } from './hooks/useOverheadSatellites'

export default function App() {
  const [selected, setSelected] = useState<{ code: string; name: string } | null>(null)
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
        />
        <CountryDropdown
          onSelect={handleCountrySelect}
          selectedCode={selected?.code ?? null}
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
