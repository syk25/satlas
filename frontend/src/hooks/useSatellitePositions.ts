import { useEffect, useState } from 'react'
import type { SatellitePosition } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const POLL_INTERVAL = 60_000

export function useSatellitePositions(): SatellitePosition[] {
  const [positions, setPositions] = useState<SatellitePosition[]>([])

  useEffect(() => {
    let cancelled = false

    const fetch_ = () =>
      fetch(`${API_BASE}/satellites/positions`)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          return res.json() as Promise<SatellitePosition[]>
        })
        .then((data) => {
          if (!cancelled) setPositions(data)
        })
        .catch(() => {})

    fetch_()
    const id = setInterval(fetch_, POLL_INTERVAL)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return positions
}
