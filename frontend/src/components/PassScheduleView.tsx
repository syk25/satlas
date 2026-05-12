import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CATEGORY_COLOR } from '../types'
import type { SatelliteCategory, SatellitePass } from '../types'

const HOUR_MS = 60 * 60 * 1000

interface Props {
  data: SatellitePass[] | null
  loading: boolean
  error: boolean
}

// Three forward-looking buckets: ≤1h / 1-6h / 6-24h. Past entries are
// dropped — they leak in because the Redis cache may have been written
// up to ~12h ago, so the timeline's `now` (server-side) is stale relative
// to the user's clock.
type Bucket = '1h' | '6h' | '24h'

function bucketFor(entryMs: number, now: number): Bucket | null {
  const offset = entryMs - now
  if (offset < 0) return null
  if (offset <= HOUR_MS) return '1h'
  if (offset <= 6 * HOUR_MS) return '6h'
  if (offset <= 24 * HOUR_MS) return '24h'
  return null
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function formatDuration(entryIso: string, exitIso: string): string {
  const ms = Date.parse(exitIso) - Date.parse(entryIso)
  return `${Math.max(1, Math.round(ms / 60_000))}m`
}

function PassRow({ pass }: { pass: SatellitePass }) {
  const { t } = useTranslation()
  const color = pass.category
    ? CATEGORY_COLOR[pass.category as SatelliteCategory]
    : '#facc15'
  return (
    <div className="pass-row">
      <div className="pass-row-time">
        <span className="pass-row-time-range">
          {formatTime(pass.entry_time)} → {formatTime(pass.exit_time)}
        </span>
        <span className="pass-row-duration">
          {formatDuration(pass.entry_time, pass.exit_time)}
        </span>
      </div>
      <div className="pass-row-main">
        <div className="pass-row-name">
          <span
            className="pass-row-dot"
            style={{ background: color, boxShadow: `0 0 4px ${color}` }}
          />
          {pass.name ?? t('satellite.norad', { id: pass.norad_id })}
        </div>
        <div className="pass-row-meta">
          {pass.orbit_class && <span>{pass.orbit_class}</span>}
          {pass.category && pass.category !== 'OTHER' && (
            <span style={{ color }}>{pass.category.replace('_', ' ')}</span>
          )}
        </div>
      </div>
    </div>
  )
}

export function PassScheduleView({ data, loading, error }: Props) {
  const { t } = useTranslation()

  // Tick every minute so passes naturally migrate between buckets and
  // drop off the top when their exit_time passes.
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])

  if (loading) return <p className="panel-status">{t('panel.loading')}</p>
  if (error) return <p className="panel-status panel-error">{t('panel.error')}</p>
  if (!data) return <p className="panel-status">{t('panel.loading')}</p>

  // Drop already-completed passes (exit < now), then bucket by entry offset.
  const futureSorted = data
    .filter((p) => Date.parse(p.exit_time) > nowMs)
    .sort((a, b) => Date.parse(a.entry_time) - Date.parse(b.entry_time))

  if (futureSorted.length === 0) {
    return <p className="panel-status">{t('schedule.noPasses')}</p>
  }

  const buckets: Record<Bucket, SatellitePass[]> = { '1h': [], '6h': [], '24h': [] }
  for (const p of futureSorted) {
    const b = bucketFor(Date.parse(p.entry_time), nowMs)
    if (b) buckets[b].push(p)
  }

  const sections: { key: Bucket; label: string; items: SatellitePass[] }[] = [
    { key: '1h', label: t('schedule.withinHour'), items: buckets['1h'] },
    { key: '6h', label: t('schedule.within6Hours'), items: buckets['6h'] },
    { key: '24h', label: t('schedule.within24Hours'), items: buckets['24h'] },
  ]

  return (
    <div className="pass-schedule">
      <p className="panel-count">
        {t('schedule.total', { count: futureSorted.length })}
      </p>
      {sections
        .filter((s) => s.items.length > 0)
        .map((s) => (
          <section key={s.key} className="pass-section">
            <h4 className="pass-section-title">
              {s.label} <span className="pass-section-count">{s.items.length}</span>
            </h4>
            <div className="pass-section-list">
              {s.items.map((p, i) => (
                <PassRow key={`${p.norad_id}-${p.entry_time}-${i}`} pass={p} />
              ))}
            </div>
          </section>
        ))}
    </div>
  )
}
