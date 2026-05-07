export interface SatelliteOverhead {
  norad_id: number
  name: string
  operator_country: string | null
  operator_name: string | null
  operator_type: string | null
  orbit_class: string | null
  line1: string
  line2: string
  entry_time: string
}
