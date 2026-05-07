import { useCallback, useState } from 'react'
import { Globe } from './components/Globe'
import { SatellitePanel } from './components/SatellitePanel'
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
        <Globe
          onCountrySelect={handleCountrySelect}
          selectedCode={selected?.code ?? null}
          satellites={data ?? []}
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
