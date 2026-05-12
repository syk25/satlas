import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useDashboardStats } from '../hooks/useDashboardStats'
import { CATEGORY_COLOR } from '../types'
import type {
  DashboardRecentLaunch,
  DashboardSatellites,
  DashboardTopCountry,
  SatelliteCategory,
} from '../types'

function useCountryNames(): Record<string, string> {
  const [names, setNames] = useState<Record<string, string>>({})
  useEffect(() => {
    fetch('/countries.geojson')
      .then((r) => r.json())
      .then((data) => {
        const lookup: Record<string, string> = {}
        for (const f of data.features) {
          const code = f.properties.ISO_A2
          const name = f.properties.NAME ?? f.properties.ADMIN
          if (code && code !== '-99' && name) lookup[code] = name
        }
        setNames(lookup)
      })
      .catch(() => {})
  }, [])
  return names
}

function StatCard({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <section className="stat-card">
      <header className="stat-card-header">
        <h3 className="stat-card-title">{title}</h3>
        {subtitle && <span className="stat-card-subtitle">{subtitle}</span>}
      </header>
      <div className="stat-card-body">{children}</div>
    </section>
  )
}

function SatelliteTotalsCard({ data }: { data: DashboardSatellites }) {
  const { t } = useTranslation()
  const max = useMemo(
    () => Math.max(1, ...Object.values(data.by_category)),
    [data.by_category]
  )
  const sortedCats = useMemo(() => {
    return (Object.entries(data.by_category) as [SatelliteCategory, number][])
      .filter(([, count]) => count > 0)
      .sort((a, b) => b[1] - a[1])
  }, [data.by_category])

  return (
    <StatCard
      title={t('dashboard.cards.totals.title')}
      subtitle={t('dashboard.cards.totals.subtitle')}
    >
      <div className="stat-totals-headline">
        <span className="stat-totals-number">{data.total.toLocaleString()}</span>
        <span className="stat-totals-unit">{t('dashboard.cards.totals.unit')}</span>
      </div>
      <div className="stat-bars">
        {sortedCats.map(([cat, count]) => (
          <div key={cat} className="stat-bar-row">
            <span className="stat-bar-label" style={{ color: CATEGORY_COLOR[cat] }}>
              {cat.replace('_', ' ')}
            </span>
            <div className="stat-bar-track">
              <div
                className="stat-bar-fill"
                style={{
                  width: `${(count / max) * 100}%`,
                  background: CATEGORY_COLOR[cat],
                }}
              />
            </div>
            <span className="stat-bar-value">{count.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </StatCard>
  )
}

function TopCountriesCard({
  data,
  names,
}: {
  data: DashboardTopCountry[]
  names: Record<string, string>
}) {
  const { t } = useTranslation()
  const max = data[0]?.passes_24h ?? 1
  if (data.length === 0) {
    return (
      <StatCard
        title={t('dashboard.cards.topCountries.title')}
        subtitle={t('dashboard.cards.topCountries.subtitle')}
      >
        <p className="stat-empty">{t('dashboard.empty')}</p>
      </StatCard>
    )
  }
  return (
    <StatCard
      title={t('dashboard.cards.topCountries.title')}
      subtitle={t('dashboard.cards.topCountries.subtitle')}
    >
      <div className="stat-bars">
        {data.map((row, i) => (
          <div key={row.cc} className="stat-bar-row">
            <span className="stat-bar-rank">{i + 1}</span>
            <span className="stat-bar-label">{names[row.cc] ?? row.cc}</span>
            <div className="stat-bar-track">
              <div
                className="stat-bar-fill"
                style={{ width: `${(row.passes_24h / max) * 100}%` }}
              />
            </div>
            <span className="stat-bar-value">{row.passes_24h.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </StatCard>
  )
}

function RecentLaunchesCard({ data }: { data: DashboardRecentLaunch[] }) {
  const { t } = useTranslation()
  if (data.length === 0) {
    return (
      <StatCard
        title={t('dashboard.cards.recentLaunches.title')}
        subtitle={t('dashboard.cards.recentLaunches.subtitle')}
      >
        <p className="stat-empty">{t('dashboard.empty')}</p>
      </StatCard>
    )
  }
  return (
    <StatCard
      title={t('dashboard.cards.recentLaunches.title')}
      subtitle={t('dashboard.cards.recentLaunches.subtitle')}
    >
      <div className="stat-launches">
        {data.map((sat) => (
          <div key={sat.norad_id} className="stat-launch-row">
            <span className="stat-launch-date">{sat.launch_date ?? ''}</span>
            <div className="stat-launch-body">
              <div className="stat-launch-name">
                {sat.category && (
                  <span
                    className="stat-launch-dot"
                    style={{
                      background: CATEGORY_COLOR[sat.category],
                      boxShadow: `0 0 4px ${CATEGORY_COLOR[sat.category]}`,
                    }}
                  />
                )}
                {sat.name}
              </div>
              <div className="stat-launch-meta">
                <span>NORAD {sat.norad_id}</span>
                {sat.operator && <span>{sat.operator}</span>}
                {sat.category && sat.category !== 'OTHER' && (
                  <span>{sat.category.replace('_', ' ')}</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </StatCard>
  )
}

export default function DashboardPage() {
  const { t } = useTranslation()
  const { data, loading, error } = useDashboardStats()
  const names = useCountryNames()

  if (loading && !data) {
    return (
      <div className="dashboard">
        <p className="dashboard-status">{t('panel.loading')}</p>
      </div>
    )
  }
  if (error && !data) {
    return (
      <div className="dashboard">
        <p className="dashboard-status panel-error">{t('panel.error')}</p>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="dashboard">
        <p className="dashboard-status">{t('panel.loading')}</p>
      </div>
    )
  }

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1 className="dashboard-title">{t('dashboard.title')}</h1>
        <p className="dashboard-tagline">{t('dashboard.tagline')}</p>
      </header>
      <div className="dashboard-grid">
        <SatelliteTotalsCard data={data.satellites} />
        <TopCountriesCard data={data.top_countries} names={names} />
        <RecentLaunchesCard data={data.recent_launches} />
      </div>
    </div>
  )
}
