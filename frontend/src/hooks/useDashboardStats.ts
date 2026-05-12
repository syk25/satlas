import { useEffect, useState } from 'react'
import type { DashboardStats } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// Backend caches the payload for 5 min; refreshing every 5 min on the client
// catches a new sweep at most one tick late without hammering the endpoint.
const REFRESH_INTERVAL_MS = 5 * 60 * 1000

interface State {
  data: DashboardStats | null
  loading: boolean
  error: boolean
}

export function useDashboardStats(): State {
  const [state, setState] = useState<State>({
    data: null,
    loading: true,
    error: false,
  })

  useEffect(() => {
    let cancelled = false

    const fetchOnce = (initial: boolean) => {
      if (initial) setState({ data: null, loading: true, error: false })

      fetch(`${API_BASE}/stats/dashboard`)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          return res.json() as Promise<DashboardStats>
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
  }, [])

  return state
}
