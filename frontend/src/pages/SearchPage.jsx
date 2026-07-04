import { useState } from 'react'
import { Search, Loader2, Globe, Hash, Filter } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'
import ResultCard from '../components/search/ResultCard'

const EXAMPLE_QUERIES = [
  'обессоливание воды сульфаты хлориды Ca Mg Na',
  'циркуляция католита электроэкстракция никеля',
  'распределение Au Ag МПГ штейн шлак',
  'закачка шахтных вод глубокие горизонты',
  'кучное выщелачивание холодный климат никель',
]

const DOC_KINDS = [
  { value: '', label: 'Все типы' },
  { value: 'publication', label: 'Публикация' },
  { value: 'patent', label: 'Патент' },
  { value: 'report', label: 'Отчёт' },
  { value: 'regulation', label: 'Норматив' },
  { value: 'experiment_catalog', label: 'Каталог экспериментов' },
]

const GEO_OPTIONS = [
  { value: '', label: 'Вся география' },
  { value: 'RU', label: 'Россия / СНГ' },
  { value: 'EN', label: 'Зарубежная практика' },
  { value: 'global', label: 'Мировая' },
]

export default function SearchPage() {
  const { auth } = useAuth()
  const [mode, setMode] = useState('semantic')
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState({
    geography: '',
    document_kind: '',
    year_from: '',
    year_to: '',
    min_confidence: '',
    verification_status: '',
  })
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState('')

  const buildFilterBody = () => {
    const body = { query, limit: 25 }
    if (filters.geography) body.geography = filters.geography
    if (filters.document_kind) body.document_kind = filters.document_kind
    if (filters.year_from) body.year_from = Number(filters.year_from)
    if (filters.year_to) body.year_to = Number(filters.year_to)
    if (filters.min_confidence) body.min_confidence = Number(filters.min_confidence)
    if (filters.verification_status) body.verification_status = filters.verification_status
    return body
  }

  const search = async (e) => {
    e?.preventDefault()
    if (query.length < 2) return
    setLoading(true)
    setError('')
    setResults(null)
    try {
      let data
      if (mode === 'numeric') {
        data = await api.numericSearch(auth, query, {
          geography: filters.geography || undefined,
          verification_status: filters.verification_status || undefined,
        })
      } else if (mode === 'compare') {
        data = await api.comparePractices(auth, query, buildFilterBody())
      } else {
        data = await api.filteredSearch(auth, buildFilterBody())
      }
      setResults(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const ranked = results?.ranked_results
    || results?.results?.map(f => ({
      result_type: 'fact',
      id: f.id,
      title: `${f.subject} —[${f.relation}]→ ${f.object}`,
      snippet: JSON.stringify(f.matched_constraint || f.properties || {}).slice(0, 300),
      score: f.confidence,
      metadata: {
        geography: f.geography,
        verification_status: f.verification_status,
        source_document: f.source_document,
      },
      raw: f,
    }))
    || []

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div className="card p-4 space-y-4">
        <div className="flex flex-wrap gap-2">
          {[
            ['semantic', Filter, 'Семантический'],
            ['numeric', Hash, 'Числовой'],
            ['compare', Globe, 'RU vs мир'],
          ].map(([id, Icon, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setMode(id)}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border',
                mode === id ? 'bg-brand-600 text-white border-brand-600' : 'border-surface-700 text-surface-300',
              )}
            >
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>

        <form onSubmit={search} className="flex gap-3">
          <input
            className="input flex-1"
            placeholder={
              mode === 'numeric'
                ? 'сульфаты < 200 мг/л, сухой остаток ≤ 1000 мг/дм³'
                : 'Материал + процесс + условия + география…'
            }
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <button type="submit" className="btn-primary shrink-0" disabled={loading}>
            {loading ? <Loader2 size={16} className="animate-spin-slow" /> : <Search size={16} />}
            Искать
          </button>
        </form>

        {mode !== 'compare' && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <select className="input text-xs py-2" value={filters.geography}
              onChange={e => setFilters(f => ({ ...f, geography: e.target.value }))}>
              {GEO_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <select className="input text-xs py-2" value={filters.document_kind}
              onChange={e => setFilters(f => ({ ...f, document_kind: e.target.value }))}>
              {DOC_KINDS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <select className="input text-xs py-2" value={filters.verification_status}
              onChange={e => setFilters(f => ({ ...f, verification_status: e.target.value }))}>
              <option value="">Любой статус</option>
              <option value="verified">verified</option>
              <option value="pending">pending</option>
              <option value="rejected">rejected</option>
            </select>
            <input className="input text-xs py-2" type="number" placeholder="Год от"
              value={filters.year_from} onChange={e => setFilters(f => ({ ...f, year_from: e.target.value }))} />
            <input className="input text-xs py-2" type="number" placeholder="Год до"
              value={filters.year_to} onChange={e => setFilters(f => ({ ...f, year_to: e.target.value }))} />
            <input className="input text-xs py-2" type="number" step="0.1" min="0" max="1" placeholder="Мин. confidence"
              value={filters.min_confidence} onChange={e => setFilters(f => ({ ...f, min_confidence: e.target.value }))} />
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {EXAMPLE_QUERIES.map(q => (
            <button key={q} type="button" className="badge bg-brand-50 text-brand-700 border border-brand-100 cursor-pointer hover:bg-brand-100"
              onClick={() => { setQuery(q); setMode('semantic') }}>
              {q.slice(0, 42)}{q.length > 42 ? '…' : ''}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="card p-4 text-red-500 text-sm">{error}</div>}

      {results && (
        <div className="space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="text-sm text-surface-400">
              {mode === 'compare' && results.comparison
                ? `RU: ${results.domestic?.verified_facts?.length ?? 0} · Global: ${results.global?.verified_facts?.length ?? 0}`
                : `Найдено: ${ranked.length} результатов`}
              {results.pipeline && <span className="ml-2 badge bg-surface-900">{results.pipeline}</span>}
            </p>
            {results.parsed && (
              <p className="text-xs text-surface-400 font-mono">{JSON.stringify(results.parsed)}</p>
            )}
          </div>

          {mode === 'compare' && results.domestic && (
            <div className="grid md:grid-cols-2 gap-4">
              <div className="card p-4">
                <h4 className="text-sm font-bold text-surface-100 mb-2">Отечественная практика (RU)</h4>
                <div className="space-y-2">
                  {(results.domestic.ranked_results || []).slice(0, 8).map((r, i) => (
                    <ResultCard key={`ru-${i}`} item={r} />
                  ))}
                </div>
              </div>
              <div className="card p-4">
                <h4 className="text-sm font-bold text-surface-100 mb-2">Мировая практика</h4>
                <div className="space-y-2">
                  {(results.global?.ranked_results || []).slice(0, 8).map((r, i) => (
                    <ResultCard key={`gl-${i}`} item={r} />
                  ))}
                </div>
              </div>
              {results.comparison?.shared_topics?.length > 0 && (
                <div className="md:col-span-2 card p-3 text-xs text-surface-400">
                  Общие темы: {results.comparison.shared_topics.slice(0, 8).join(', ')}
                </div>
              )}
            </div>
          )}

          {mode !== 'compare' && ranked.length === 0 && (
            <div className="card p-6 text-center text-surface-400 text-sm">
              Ничего не найдено. Загрузите отчёты/JSON или уточните фильтры.
            </div>
          )}

          {mode !== 'compare' && ranked.slice(0, 25).map((r, i) => (
            <ResultCard key={`${r.result_type}-${r.id}-${i}`} item={r} />
          ))}
        </div>
      )}
    </div>
  )
}
