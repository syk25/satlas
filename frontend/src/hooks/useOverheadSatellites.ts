import { useEffect, useState } from 'react'
import type { SatelliteOverhead } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

interface State {
  data: SatelliteOverhead[] | null
  loading: boolean
  error: boolean
}

export function useOverheadSatellites(countryCode: string | null): State {
  const [state, setState] = useState<State>({
    data: null,
    loading: false,
    error: false,
  })

  useEffect(() => {
    if (!countryCode) {
      setState({ data: null, loading: false, error: false })
      return
    }

    let cancelled = false
    setState({ data: null, loading: true, error: false })

    fetch(`${API_BASE}/satellites/overhead/${countryCode}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<SatelliteOverhead[]>
      })
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ data: null, loading: false, error: true })
      })

    return () => {
      cancelled = true
    }
  }, [countryCode])

  return state
}
