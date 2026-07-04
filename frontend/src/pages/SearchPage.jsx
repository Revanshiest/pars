import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Search, Loader2, Network, FileText, GitBranch, Database,
  Filter, Globe, Calculator, Bot, BookOpen, AlertTriangle, Download, Sparkles,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

const TABS = [
  { id: 'search', label: 'Поиск', icon: Search },
  { id: 'numeric', label: 'Числа', icon: Calculator },
  { id: 'compare', label: 'RU vs мир', icon: Globe },
  { id: 'agent', label: 'Агент', icon: Bot },
  { id: 'review', label: 'Литобзор', icon: BookOpen },
  { id: 'gaps', label: 'Пробелы', icon: AlertTriangle },
  { id: 'export', label: 'Экспорт', icon: Download },
]

const TYPE_META = {
  entity: { label: 'Сущность', icon: Network, color: 'bg-violet-100 text-violet-700 border-violet-200' },
  chunk: { label: 'Фрагмент', icon: FileText, color: 'bg-brand-100 text-brand-700 border-brand-200' },
  fact: { label: 'Факт', icon: Database, color: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  graph_edge: { label: 'Связь', icon: GitBranch, color: 'bg-amber-100 text-amber-700 border-amber-200' },
}

const ENTITY_TYPES = ['Material', 'Process', 'Equipment', 'Parameter', 'Expert', 'Publication', 'Experiment']
const DOC_KINDS = ['', 'patent', 'regulation', 'publication', 'report', 'experiment_catalog']
const GEO = ['', 'RU', 'EN', 'global']

const DEFAULT_FILTERS = {
  entity_type: '', geography: '', min_confidence: '', verification_status: '',
  year_from: '', year_to: '', author: '', document_kind: '', graph_depth: 3, limit: 15,
}

function ResultCard({ item }) {
  const meta = TYPE_META[item.result_type] || { label: item.result_type, icon: FileText, color: 'bg-surface-900 text-surface-300 border-surface-700' }
  const Icon = meta.icon
  const entityName = item.result_type === 'entity' ? item.title
    : item.result_type === 'fact' ? item.raw?.subject || item.title?.split(' —[')[0]
      : item.metadata?.name || item.metadata?.source

  return (
    <div className="card-hover p-4 group">
      <div className="flex items-start gap-3">
        <div className={clsx('w-9 h-9 rounded-xl border flex items-center justify-center shrink-0', meta.color)}>
          <Icon size={15} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className={clsx('badge border', meta.color)}>{meta.label}</span>
            {item.score != null && (
              <span className="text-xs text-surface-400 tabular-nums">score {item.score.toFixed(3)}</span>
            )}
            {(item.sources || []).map(s => (
              <span key={s} className="badge bg-surface-900 text-surface-400 border border-surface-700">{s}</span>
            ))}
          </div>
          <p className="text-sm font-semibold text-surface-100 leading-snug">{item.title}</p>
          {item.snippet && <p className="text-xs text-surface-400 mt-1.5 line-clamp-3">{item.snippet}</p>}
          {item.metadata?.verification_status && (
            <p className="text-[10px] text-surface-400 mt-1">Статус: {item.metadata.verification_status}</p>
          )}
          {(item.result_type === 'entity' || item.result_type === 'fact' || item.result_type === 'graph_edge') && entityName && (
            <Link
              to={`/graph?entity=${encodeURIComponent(entityName)}`}
              className="inline-flex items-center gap-1 mt-2 text-xs text-brand-600 hover:text-brand-700 font-medium opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <Network size={12} /> Открыть в графе
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}

function MarkdownBlock({ text }) {
  if (!text) return null
  return (
    <div className="prose prose-sm max-w-none text-surface-200 whitespace-pre-wrap leading-relaxed">
      {text}
    </div>
  )
}

export default function SearchPage() {
  const { auth, user } = useAuth()
  const [tab, setTab] = useState('search')
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [showFilters, setShowFilters] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [results, setResults] = useState(null)

  const [reviewTopic, setReviewTopic] = useState('')
  const [reviewResult, setReviewResult] = useState(null)
  const [gapQuery, setGapQuery] = useState('')
  const [gapResult, setGapResult] = useState(null)
  const [exportTopic, setExportTopic] = useState('')
  const [exportFmt, setExportFmt] = useState('md')
  const [exportBusy, setExportBusy] = useState(false)

  const canCompare = ['project_manager', 'admin', 'analyst'].includes(user?.role)
  const canSynthesis = ['analyst', 'project_manager', 'admin', 'researcher'].includes(user?.role)
  const canExport = ['analyst', 'project_manager', 'admin'].includes(user?.role)

  const buildSearchBody = () => {
    const body = { query: query.trim(), limit: Number(filters.limit) || 15, graph_depth: Number(filters.graph_depth) || 3 }
    if (filters.entity_type) body.entity_type = filters.entity_type
    if (filters.geography) body.geography = filters.geography
    if (filters.min_confidence) body.min_confidence = Number(filters.min_confidence)
    if (filters.verification_status) body.verification_status = filters.verification_status
    if (filters.author) body.author = filters.author
    if (filters.document_kind) body.document_kind = filters.document_kind
    if (filters.year_from) body.year_from = Number(filters.year_from)
    if (filters.year_to) body.year_to = Number(filters.year_to)
    return body
  }

  const runSearch = async (e) => {
    e?.preventDefault()
    if (query.trim().length < 2) return
    setLoading(true)
    setError('')
    setResults(null)
    try {
      let data
      if (tab === 'search') {
        data = await api.hybridSearch(auth, buildSearchBody())
      } else if (tab === 'numeric') {
        data = await api.numericSearch(auth, { query: query.trim(), limit: 50, geography: filters.geography || undefined })
      } else if (tab === 'compare') {
        data = await api.comparePractices(auth, { query: query.trim(), limit: 15, year_from: filters.year_from ? Number(filters.year_from) : undefined, year_to: filters.year_to ? Number(filters.year_to) : undefined })
      } else if (tab === 'agent') {
        data = await api.agentSearch(auth, query.trim())
      }
      setResults(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const runReview = async (e) => {
    e.preventDefault()
    if (reviewTopic.length < 3) return
    setLoading(true)
    setError('')
    try {
      setReviewResult(await api.literatureReview(auth, { topic: reviewTopic, geography: filters.geography || undefined }))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const runGaps = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = gapQuery.trim()
        ? await api.ontologyGaps(auth, { query: gapQuery })
        : await api.analyticsGaps(auth, {})
      setGapResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const runExport = async (e) => {
    e.preventDefault()
    if (!exportTopic.trim() || !canExport) return
    setExportBusy(true)
    setError('')
    try {
      const res = await api.exportReport(auth, { topic: exportTopic.trim(), format: exportFmt })
      if (res.content) {
        const blob = new Blob([res.content], { type: exportFmt === 'jsonld' ? 'application/ld+json' : 'text/markdown' })
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = `${exportTopic.slice(0, 40)}.${exportFmt === 'jsonld' ? 'jsonld' : 'md'}`
        a.click()
      } else if (res.path) {
        window.open(api.exportDownloadUrl(exportTopic.trim()), '_blank')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setExportBusy(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div>
        <h2 className="text-lg font-bold text-surface-100 flex items-center gap-2">
          <Sparkles size={20} className="text-brand-600" />
          Исследование знаний
        </h2>
        <p className="text-xs text-surface-400 mt-1">
          Гибридный поиск, числовые ограничения, сравнение практик, литобзор и анализ пробелов
        </p>
      </div>

      <div className="flex flex-wrap gap-1 p-1 bg-surface-900 rounded-2xl border border-surface-700">
        {TABS.map(({ id, label, icon: Icon }) => {
          if (id === 'compare' && !canCompare) return null
          if ((id === 'review' || id === 'export') && id === 'export' && !canExport) return null
          return (
            <button
              key={id}
              type="button"
              onClick={() => { setTab(id); setResults(null); setError('') }}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all',
                tab === id ? 'bg-brand-600 text-white shadow-brand' : 'text-surface-400 hover:text-surface-100 hover:bg-white/5',
              )}
            >
              <Icon size={13} /> {label}
            </button>
          )
        })}
      </div>

      {error && <div className="card p-4 border-red-200 bg-red-50 text-red-600 text-sm">{error}</div>}

      {['search', 'numeric', 'compare', 'agent'].includes(tab) && (
        <>
          <form onSubmit={runSearch} className="card p-4 space-y-3">
            <div className="flex gap-3">
              <input
                className="input flex-1"
                placeholder={
                  tab === 'numeric' ? 'сульфаты < 200 мг/л, температура 60–80 °C…'
                    : tab === 'compare' ? 'циркуляция католита электроэкстракция никель…'
                      : 'heap leaching nickel, обессоливание воды…'
                }
                value={query}
                onChange={e => setQuery(e.target.value)}
              />
              <button type="submit" className="btn-primary shrink-0" disabled={loading || query.length < 2}>
                {loading ? <Loader2 size={16} className="animate-spin-slow" /> : <Search size={16} />}
                {tab === 'agent' ? 'Спросить' : 'Искать'}
              </button>
            </div>
            {tab === 'search' && (
              <button type="button" className="btn-ghost text-xs" onClick={() => setShowFilters(v => !v)}>
                <Filter size={13} /> {showFilters ? 'Скрыть фильтры' : 'Фильтры и диапазоны'}
              </button>
            )}
            {showFilters && tab === 'search' && (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-2 border-t border-surface-700">
                <div>
                  <label className="label mb-1 block">Тип сущности</label>
                  <select className="input text-sm" value={filters.entity_type}
                    onChange={e => setFilters(f => ({ ...f, entity_type: e.target.value }))}>
                    <option value="">Любой</option>
                    {ENTITY_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label mb-1 block">География</label>
                  <select className="input text-sm" value={filters.geography}
                    onChange={e => setFilters(f => ({ ...f, geography: e.target.value }))}>
                    {GEO.map(g => <option key={g} value={g}>{g || 'Любая'}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label mb-1 block">Вид документа</label>
                  <select className="input text-sm" value={filters.document_kind}
                    onChange={e => setFilters(f => ({ ...f, document_kind: e.target.value }))}>
                    {DOC_KINDS.map(d => <option key={d} value={d}>{d || 'Любой'}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label mb-1 block">Мин. достоверность</label>
                  <input type="number" step="0.1" min="0" max="1" className="input text-sm"
                    value={filters.min_confidence} onChange={e => setFilters(f => ({ ...f, min_confidence: e.target.value }))} />
                </div>
                <div>
                  <label className="label mb-1 block">Статус верификации</label>
                  <select className="input text-sm" value={filters.verification_status}
                    onChange={e => setFilters(f => ({ ...f, verification_status: e.target.value }))}>
                    <option value="">Любой</option>
                    <option value="verified">verified</option>
                    <option value="pending">pending</option>
                    <option value="in_review">in_review</option>
                  </select>
                </div>
                <div>
                  <label className="label mb-1 block">Глубина графа</label>
                  <input type="number" min="1" max="4" className="input text-sm"
                    value={filters.graph_depth} onChange={e => setFilters(f => ({ ...f, graph_depth: e.target.value }))} />
                </div>
                <div>
                  <label className="label mb-1 block">Год от</label>
                  <input type="number" className="input text-sm" placeholder="2020"
                    value={filters.year_from} onChange={e => setFilters(f => ({ ...f, year_from: e.target.value }))} />
                </div>
                <div>
                  <label className="label mb-1 block">Год до</label>
                  <input type="number" className="input text-sm" placeholder="2026"
                    value={filters.year_to} onChange={e => setFilters(f => ({ ...f, year_to: e.target.value }))} />
                </div>
                <div>
                  <label className="label mb-1 block">Автор</label>
                  <input className="input text-sm" value={filters.author}
                    onChange={e => setFilters(f => ({ ...f, author: e.target.value }))} />
                </div>
              </div>
            )}
          </form>

          {results && tab === 'agent' && (
            <div className="card p-5 space-y-4">
              <MarkdownBlock text={results.answer} />
              {results.tool_calls?.length > 0 && (
                <details className="text-xs text-surface-400">
                  <summary className="cursor-pointer">Инструменты ({results.tool_calls.length})</summary>
                  <pre className="mt-2 p-3 bg-surface-900 rounded-xl overflow-auto">{JSON.stringify(results.tool_calls, null, 2)}</pre>
                </details>
              )}
            </div>
          )}

          {results && tab === 'compare' && (
            <div className="card p-5 space-y-4">
              <h3 className="section-title text-sm">Сравнение практик</h3>
              <MarkdownBlock text={results.comparison?.summary || JSON.stringify(results.comparison, null, 2)} />
              {results.comparison?.ru_only_topics?.length > 0 && (
                <div>
                  <p className="label mb-2">Только RU</p>
                  <div className="flex flex-wrap gap-1">
                    {results.comparison.ru_only_topics.map(t => (
                      <span key={t} className="badge bg-red-50 text-red-700 border border-red-200">{t}</span>
                    ))}
                  </div>
                </div>
              )}
              {results.comparison?.global_only_topics?.length > 0 && (
                <div>
                  <p className="label mb-2">Только мировая</p>
                  <div className="flex flex-wrap gap-1">
                    {results.comparison.global_only_topics.map(t => (
                      <span key={t} className="badge bg-blue-50 text-blue-700 border border-blue-200">{t}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {results && tab === 'numeric' && (
            <div className="space-y-3">
              <p className="text-sm text-surface-400">
                Найдено: {results.matches?.length || results.facts?.length || 0} совпадений
                {results.parsed_constraints && (
                  <span className="ml-2 text-xs">({JSON.stringify(results.parsed_constraints)})</span>
                )}
              </p>
              {(results.matches || results.facts || []).map((m, i) => (
                <div key={i} className="card p-4 text-sm">
                  <p className="font-semibold text-surface-100">{m.subject || m.parameter} → {m.object || m.value}</p>
                  {m.source_document && <p className="text-xs text-surface-400 mt-1">{m.source_document}</p>}
                </div>
              ))}
            </div>
          )}

          {results && ['search'].includes(tab) && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm text-surface-400">
                  Найдено: {results.ranked_results?.length || 0}
                  {results.expanded_query && (
                    <span className="ml-2 text-xs">расширено: {results.expanded_query}</span>
                  )}
                </p>
                {results.counts && (
                  <p className="text-xs text-surface-400">
                    chunks {results.counts.chunks} · entities {results.counts.entities} · facts {results.counts.facts}
                  </p>
                )}
              </div>
              {(results.ranked_results || []).map((r, i) => (
                <ResultCard key={`${r.result_type}-${r.id}-${i}`} item={r} />
              ))}
            </div>
          )}
        </>
      )}

      {tab === 'review' && canSynthesis && (
        <>
          <form onSubmit={runReview} className="card p-4 flex gap-3">
            <input className="input flex-1" placeholder="Тема литобзора: циркуляция католита, обессоливание…"
              value={reviewTopic} onChange={e => setReviewTopic(e.target.value)} minLength={3} />
            <button type="submit" className="btn-primary shrink-0" disabled={loading || reviewTopic.length < 3}>
              {loading ? <Loader2 size={16} className="animate-spin-slow" /> : <BookOpen size={16} />}
              Синтез
            </button>
          </form>
          {reviewResult && (
            <div className="card p-5 space-y-4">
              <MarkdownBlock text={reviewResult.summary || reviewResult.synthesis} />
              {reviewResult.consensus?.length > 0 && (
                <div>
                  <p className="label mb-2">Консенсус</p>
                  <ul className="text-sm space-y-1 text-surface-300">
                    {reviewResult.consensus.map((c, i) => <li key={i}>• {c}</li>)}
                  </ul>
                </div>
              )}
              {reviewResult.disagreements?.length > 0 && (
                <div>
                  <p className="label mb-2 text-amber-600">Разногласия</p>
                  <ul className="text-sm space-y-1 text-amber-700">
                    {reviewResult.disagreements.map((c, i) => <li key={i}>• {c}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {tab === 'gaps' && (
        <>
          <form onSubmit={runGaps} className="card p-4 flex gap-3">
            <input className="input flex-1" placeholder="Запрос: холодный климат + HL + никель (пусто = все сценарии)"
              value={gapQuery} onChange={e => setGapQuery(e.target.value)} />
            <button type="submit" className="btn-primary shrink-0" disabled={loading}>
              {loading ? <Loader2 size={16} className="animate-spin-slow" /> : <AlertTriangle size={16} />}
              Анализ
            </button>
          </form>
          {gapResult && (
            <div className="space-y-3">
              <p className="text-sm text-surface-400">
                Сценариев: {gapResult.scenarios_analyzed ?? '—'} · критических пробелов: {gapResult.critical_gaps ?? gapResult.gaps?.length ?? 0}
              </p>
              {(gapResult.ontology_gaps || gapResult.gaps || []).map((g, i) => (
                <div key={g.scenario_id || i} className={clsx('card p-4', g.is_gap && 'border-amber-300 bg-amber-50/50')}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm font-bold text-surface-100">{g.label || g.topic}</span>
                    {g.gap_severity && (
                      <span className={clsx('badge border',
                        g.gap_severity === 'critical' ? 'bg-red-100 text-red-700 border-red-200' : 'bg-amber-100 text-amber-700 border-amber-200',
                      )}>{g.gap_severity}</span>
                    )}
                  </div>
                  <p className="text-xs text-surface-400">{g.recommendation || g.description}</p>
                  {g.coverage && (
                    <p className="text-[10px] text-surface-400 mt-2">Покрытие: {JSON.stringify(g.coverage)}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {tab === 'export' && canExport && (
        <form onSubmit={runExport} className="card p-5 space-y-4">
          <div>
            <label className="label mb-1.5 block">Тема отчёта</label>
            <input className="input" value={exportTopic} onChange={e => setExportTopic(e.target.value)} required />
          </div>
          <div>
            <label className="label mb-1.5 block">Формат</label>
            <select className="input max-w-xs" value={exportFmt} onChange={e => setExportFmt(e.target.value)}>
              <option value="md">Markdown</option>
              <option value="pdf">PDF</option>
              <option value="jsonld">JSON-LD</option>
            </select>
          </div>
          <button type="submit" className="btn-primary" disabled={exportBusy}>
            {exportBusy ? <Loader2 size={16} className="animate-spin-slow" /> : <Download size={16} />}
            Сформировать отчёт
          </button>
        </form>
      )}
    </div>
  )
}
