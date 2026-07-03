import { useState } from 'react'
import { Search, Loader2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

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
          placeholder="Запрос: heap leaching nickel холодный климат…"
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
          <p className="text-sm text-surface-400">
            Найдено: {results.ranked_results?.length || 0} результатов
          </p>
          {(results.ranked_results || []).slice(0, 15).map((r, i) => (
            <div key={i} className="card p-4">
              <div className="flex items-center gap-2 mb-1">
                <span className="badge bg-brand-100 text-brand-700">{r.result_type || 'item'}</span>
                {r.score != null && (
                  <span className="text-xs text-surface-400">score: {r.score.toFixed(3)}</span>
                )}
              </div>
              <p className="text-sm text-surface-100">{r.title || r.snippet || JSON.stringify(r.raw || r).slice(0, 200)}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
