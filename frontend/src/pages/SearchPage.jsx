import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Loader2, Network, FileText, GitBranch, Database } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

const TYPE_META = {
  entity: { label: 'Сущность', icon: Network, color: 'bg-violet-100 text-violet-700 border-violet-200' },
  chunk: { label: 'Фрагмент', icon: FileText, color: 'bg-brand-100 text-brand-700 border-brand-200' },
  fact: { label: 'Факт', icon: Database, color: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  graph_edge: { label: 'Связь', icon: GitBranch, color: 'bg-amber-100 text-amber-700 border-amber-200' },
}

function ResultCard({ item }) {
  const meta = TYPE_META[item.result_type] || { label: item.result_type, icon: FileText, color: 'bg-surface-900 text-surface-300 border-surface-700' }
  const Icon = meta.icon
  const entityName = item.result_type === 'entity'
    ? item.title
    : item.result_type === 'fact'
      ? item.raw?.subject || item.title?.split(' —[')[0]
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
          {item.snippet && (
            <p className="text-xs text-surface-400 mt-1.5 line-clamp-3">{item.snippet}</p>
          )}
          {item.metadata?.type && (
            <p className="text-[10px] text-surface-400 mt-1">Тип: {item.metadata.type}</p>
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

export default function SearchPage() {
  const { auth } = useAuth()
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState('')

  const search = async (e) => {
    e.preventDefault()
    if (query.length < 2) return
    setLoading(true)
    setError('')
    try {
      const data = await api.hybridSearch(auth, query)
      setResults(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <form onSubmit={search} className="card p-4 flex gap-3">
        <input
          className="input flex-1"
          placeholder="Запрос: heap leaching nickel, обессоливание воды…"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? <Loader2 size={16} className="animate-spin-slow" /> : <Search size={16} />}
          Искать
        </button>
      </form>

      {error && <div className="card p-4 text-red-500 text-sm">{error}</div>}

      {results && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm text-surface-400">
              Найдено: {results.ranked_results?.length || 0} результатов
            </p>
            {results.counts && (
              <p className="text-xs text-surface-400">
                chunks {results.counts.chunks} · entities {results.counts.entities} · facts {results.counts.facts}
              </p>
            )}
          </div>
          {(results.ranked_results || []).slice(0, 20).map((r, i) => (
            <ResultCard key={`${r.result_type}-${r.id}-${i}`} item={r} />
          ))}
        </div>
      )}
    </div>
  )
}
