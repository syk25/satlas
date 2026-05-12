export interface SatellitePosition {
  norad_id: number
  name: string
  lat: number
  lon: number
}

export type SatelliteCategory =
  | 'STATION'
  | 'WEATHER'
  | 'GNSS'
  | 'MILITARY'
  | 'AMATEUR'
  | 'COMMERCIAL'
  | 'EARTH_OBS'
  | 'SCIENTIFIC'
  | 'OTHER'

export const CATEGORY_COLOR: Record<SatelliteCategory, string> = {
  STATION: '#ffffff',
  WEATHER: '#60a5fa',
  GNSS: '#34d399',
  MILITARY: '#f87171',
  AMATEUR: '#a78bfa',
  COMMERCIAL: '#facc15',
  EARTH_OBS: '#fb923c',
  SCIENTIFIC: '#22d3ee',
  OTHER: 'rgba(255,255,255,0.3)',
}

export interface SatelliteOverhead {
  norad_id: number
  name: string
  category: SatelliteCategory | null
  operator: string | null
  operator_name: string | null
  operator_type: string | null
  orbit_class: string | null
  launch_date: string | null
  decay_date: string | null
  international_designator: string | null
  object_type: string | null
  rcs_size: string | null
  line1: string
  line2: string
  entry_time: string
  exit_time: string
  passes_24h: number | null
}

export type OverheadSort = 'entry' | 'frequency'

export interface SatellitePass {
  norad_id: number
  name: string | null
  category: SatelliteCategory | null
  orbit_class: string | null
  entry_time: string
  exit_time: string
}

export type PanelTab = 'overhead' | 'schedule'
