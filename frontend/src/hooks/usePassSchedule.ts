import { useEffect, useState } from 'react'
import type { SatellitePass } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// The backend pass timeline covers a forward 24h window and is rebuilt on
// the ~12h visits/recompute cron. Refreshing every 30 min lets us pick up
// a fresh sweep without hammering the endpoint.
const REFRESH_INTERVAL_MS = 30 * 60 * 1000

interface State {
  data: SatellitePass[] | null
  loading: boolean
  error: boolean
}

export function usePassSchedule(countryCode: string | null): State {
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

      fetch(`${API_BASE}/satellites/passes/${countryCode}`)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          return res.json() as Promise<SatellitePass[]>
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
  }, [countryCode])

  return state
}
