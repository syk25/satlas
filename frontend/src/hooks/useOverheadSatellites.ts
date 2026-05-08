import { useEffect, useState } from 'react'
import type { SatelliteOverhead } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// Half the server-side prediction window (30min) — guarantees no coverage gap.
// See ADR-018.
const REFRESH_INTERVAL_MS = 15 * 60 * 1000

interface State {
  data: SatelliteOverhead[] | null
  loading: boolean
  error: boolean
}

export function useOverheadSatellites(
  countryCode: string | null,
  includeInactive: boolean = false
): State {
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

    const fetchOnce = (initial: boolean) => {
      if (initial) setState({ data: null, loading: true, error: false })

      const url = `${API_BASE}/satellites/overhead/${countryCode}${
        includeInactive ? '?include_inactive=true' : ''
      }`

      fetch(url)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          return res.json() as Promise<SatelliteOverhead[]>
        })
        .then((data) => {
          if (!cancelled) setState({ data, loading: false, error: false })
        })
        .catch(() => {
          if (!cancelled)
            setState((prev) => ({
              data: prev.data,
              loading: false,
              error: prev.data === null,
            }))
        })
    }

    fetchOnce(true)
    const interval = setInterval(() => fetchOnce(false), REFRESH_INTERVAL_MS)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [countryCode, includeInactive])

  return state
}
