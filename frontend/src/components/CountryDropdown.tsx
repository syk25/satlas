import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

interface Country {
  code: string
  name: string
}

interface Props {
  onSelect: (code: string, name: string) => void
  selectedCode: string | null
}

export function CountryDropdown({ onSelect, selectedCode }: Props) {
  const { t } = useTranslation()
  const [countries, setCountries] = useState<Country[]>([])
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch('/countries.geojson')
      .then((r) => r.json())
      .then((data) => {
        const list: Country[] = data.features
          .map((f: any) => ({
            code: f.properties.ISO_A2,
            name: f.properties.NAME ?? f.properties.ADMIN ?? '',
          }))
          .filter((c: Country) => c.code && c.code !== '-99' && c.name)
          .sort((a: Country, b: Country) => a.name.localeCompare(b.name))
        setCountries(list)
      })
  }, [])

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim()
    return q ? countries.filter((c) => c.name.toLowerCase().includes(q)) : countries
  }, [countries, query])

  const selected = countries.find((c) => c.code === selectedCode)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleOpen = () => {
    setOpen((v) => !v)
    if (!open) setTimeout(() => inputRef.current?.focus(), 50)
  }

  const handleSelect = (country: Country) => {
    onSelect(country.code, country.name)
    setQuery('')
    setOpen(false)
  }

  return (
    <div ref={containerRef} className="country-dropdown">
      <button className="country-trigger" onClick={handleOpen}>
        <span className="country-trigger-icon">◎</span>
        <span className="country-trigger-label">
          {selected?.name ?? t('dropdown.placeholder')}
        </span>
        <span className="country-trigger-arrow">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="country-panel">
          <input
            ref={inputRef}
            className="country-search"
            placeholder={t('dropdown.search')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="country-list">
            {filtered.length === 0 && (
              <div className="country-empty">{t('dropdown.noResults')}</div>
            )}
            {filtered.map((c) => (
              <button
                key={c.code}
                className={`country-option${c.code === selectedCode ? ' active' : ''}`}
                onClick={() => handleSelect(c)}
              >
                {c.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
