import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart3, Loader2, AlertTriangle, CheckCircle, Database, BookOpen, Globe, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

function StatCard({ label, value, icon: Icon, color, href }) {
  const inner = (
    <div className={clsx('card p-5 hover:shadow-card-hover transition-all', href && 'cursor-pointer')}>
      <div className="flex items-start justify-between">
        <div>
          <p className="label mb-1">{label}</p>
          <p className="text-2xl font-black text-surface-100 tabular-nums">{value ?? '—'}</p>
        </div>
        <div className={clsx('w-10 h-10 rounded-xl flex items-center justify-center', color)}>
          <Icon size={18} />
        </div>
      </div>
    </div>
  )
  return href ? <Link to={href}>{inner}</Link> : inner
}

export default function DashboardPage() {
  const { auth } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setData(await api.dashboard(auth))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [auth])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-surface-400">
        <Loader2 size={22} className="animate-spin-slow mr-2" /> Загрузка метрик…
      </div>
    )
  }

  if (error) {
    return <div className="card p-4 text-red-600 text-sm max-w-lg mx-auto">{error}</div>
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-surface-100 flex items-center gap-2">
            <BarChart3 size={20} className="text-brand-600" />
            Дашборд R&D
          </h2>
          <p className="text-xs text-surface-400 mt-1">Покрытие знаний, верификация и зоны риска</p>
        </div>
        <button type="button" className="btn-ghost text-xs" onClick={load}>
          <RefreshCw size={13} /> Обновить
        </button>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Фактов в графе" value={data.facts_total} icon={Database} color="bg-brand-100 text-brand-700" />
        <StatCard label="Верифицировано" value={data.verified} icon={CheckCircle} color="bg-emerald-100 text-emerald-700" href="/verify" />
        <StatCard label="Ожидают проверки" value={data.pending_verification} icon={AlertTriangle} color="bg-amber-100 text-amber-700" href="/verify" />
        <StatCard label="Противоречия" value={data.contradictions} icon={AlertTriangle} color="bg-red-100 text-red-700" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="card p-5">
          <h3 className="section-title text-sm mb-4 flex items-center gap-2">
            <Globe size={15} /> По географии
          </h3>
          <div className="space-y-2">
            {Object.entries(data.facts_by_geography || {}).map(([geo, cnt]) => (
              <div key={geo} className="flex items-center gap-3">
                <span className="text-xs font-medium w-16 text-surface-400">{geo}</span>
                <div className="flex-1 h-2 bg-surface-900 rounded-full overflow-hidden">
                  <div className="h-full bg-brand-500 rounded-full" style={{ width: `${Math.min(100, (cnt / data.facts_total) * 100)}%` }} />
                </div>
                <span className="text-xs tabular-nums text-surface-300 w-8 text-right">{cnt}</span>
              </div>
            ))}
            {!Object.keys(data.facts_by_geography || {}).length && (
              <p className="text-sm text-surface-400">Нет данных по географии</p>
            )}
          </div>
        </div>

        <div className="card p-5">
          <h3 className="section-title text-sm mb-4 flex items-center gap-2">
            <BookOpen size={15} /> Глоссарий
          </h3>
          <p className="text-2xl font-black text-surface-100">{data.glossary_terms}</p>
          <p className="text-xs text-surface-400 mb-3">терминов</p>
          <div className="flex flex-wrap gap-1">
            {Object.entries(data.glossary_by_domain || {}).map(([d, c]) => (
              <span key={d} className="badge bg-surface-900 text-surface-300 border border-surface-700">
                {d || 'общий'}: {c}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="card p-5">
        <h3 className="section-title text-sm mb-4">Типы сущностей</h3>
        <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-2">
          {Object.entries(data.facts_by_entity_type || {}).map(([t, c]) => (
            <div key={t} className="flex justify-between p-2 rounded-lg bg-surface-900 text-sm">
              <span className="text-surface-300">{t}</span>
              <span className="font-semibold tabular-nums">{c}</span>
            </div>
          ))}
        </div>
      </div>

      {data.risk_zones_low_coverage?.length > 0 && (
        <div className="card p-5 border-amber-200 bg-amber-50/30">
          <h3 className="section-title text-sm mb-3 text-amber-800">Зоны риска (мало источников)</h3>
          <div className="flex flex-wrap gap-2">
            {data.risk_zones_low_coverage.map(r => (
              <span key={r.subject_type} className="badge bg-amber-100 text-amber-800 border border-amber-200">
                {r.subject_type}: {r.c} фактов
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
