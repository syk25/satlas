import { useCallback, useState } from 'react'
import { Globe } from './components/Globe'
import { SatellitePanel } from './components/SatellitePanel'

export default function App() {
  const [selected, setSelected] = useState<{ code: string; name: string } | null>(null)

  const handleCountrySelect = useCallback((code: string, name: string) => {
    setSelected({ code, name })
  }, [])

  return (
    <div className="layout">
      <div className="globe-container">
        <Globe
          onCountrySelect={handleCountrySelect}
          selectedCode={selected?.code ?? null}
        />
      </div>
      <SatellitePanel
        countryCode={selected?.code ?? null}
        countryName={selected?.name ?? null}
      />
    </div>
  )
}
