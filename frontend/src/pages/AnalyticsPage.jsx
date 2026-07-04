import { useCallback, useEffect, useState } from 'react'
import {
  BarChart3, Loader2, BookOpen, GitCompare, Download, AlertTriangle, Sparkles,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

const GAP_PRESETS = [
  { material: 'никель', process: 'выщелачивание', climate: 'холодный', label: 'Холод + HL + Ni' },
  { material: 'никель', process: 'электроэкстракция', climate: 'холодный', label: 'Холод + EW + Ni' },
  { material: 'медь', process: 'электроэкстракция', geography: 'global', label: 'EW медь' },
  { query: 'шахтные воды закачка', label: 'Шахтные воды' },
]

const CAN_SYNTHESIS = new Set(['analyst', 'project_manager', 'admin'])
const CAN_DASHBOARD = new Set(['project_manager', 'admin'])
const CAN_EXPORT = new Set(['analyst', 'project_manager', 'admin'])

export default function AnalyticsPage() {
  const { auth, user } = useAuth()
  const [tab, setTab] = useState('gaps')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [topic, setTopic] = useState('электроэкстракция никеля')
  const [techs, setTechs] = useState('heap leaching, electrowinning, fluidized bed')
  const [dashboard, setDashboard] = useState(null)
  const [gaps, setGaps] = useState(null)
  const [review, setReview] = useState(null)
  const [compare, setCompare] = useState(null)
  const [exportMsg, setExportMsg] = useState('')

  useEffect(() => {
    if (tab === 'dashboard' && CAN_DASHBOARD.has(user?.role)) {
      api.dashboard(auth).then(setDashboard).catch(e => setError(e.message))
    }
  }, [tab, auth, user?.role])

  const runGaps = async (preset) => {
    setLoading(true)
    setError('')
    try {
      const data = preset.query
        ? await api.knowledgeGaps(auth, { query: preset.query })
        : await api.ontologyGaps(auth, preset)
      setGaps(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const runReview = async (e) => {
    e.preventDefault()
    if (!CAN_SYNTHESIS.has(user?.role)) return
    setLoading(true)
    setError('')
    try {
      setReview(await api.literatureReview(auth, topic, { use_llm: false }))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const runCompare = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const list = techs.split(',').map(s => s.trim()).filter(Boolean)
      setCompare(await api.compareTechnologies(auth, list))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const doExport = async (format) => {
    setExportMsg('')
    try {
      const res = await api.exportReport(auth, topic, format)
      setExportMsg(`Экспорт ${format}: ${res.path || 'готово'}`)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div className="flex flex-wrap gap-2">
        {[
          CAN_DASHBOARD.has(user?.role) && ['dashboard', BarChart3, 'Дашборд'],
          ['gaps', AlertTriangle, 'Пробелы'],
          CAN_SYNTHESIS.has(user?.role) && ['review', BookOpen, 'Литобзор'],
          ['compare', GitCompare, 'Сравнение'],
          CAN_EXPORT.has(user?.role) && ['export', Download, 'Экспорт'],
        ].filter(Boolean).map(([id, Icon, label]) => (
          <button key={id} type="button" onClick={() => setTab(id)}
            className={clsx('flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border',
              tab === id ? 'bg-brand-600 text-white border-brand-600' : 'border-surface-700')}>
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      {error && <div className="card p-4 text-red-500 text-sm">{error}</div>}

      {tab === 'dashboard' && dashboard && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            ['Фактов', dashboard.facts_total],
            ['Verified', dashboard.verified],
            ['Pending', dashboard.pending_verification],
            ['Противоречий', dashboard.contradictions],
            ['Глоссарий', dashboard.glossary_terms],
          ].map(([l, v]) => (
            <div key={l} className="card p-4 text-center">
              <div className="text-2xl font-black text-brand-600">{v ?? 0}</div>
              <div className="text-xs text-surface-400">{l}</div>
            </div>
          ))}
          {dashboard.risk_zones_low_coverage?.length > 0 && (
            <div className="card p-4 sm:col-span-2 lg:col-span-4">
              <h4 className="text-sm font-bold mb-2">Зоны риска (мало данных)</h4>
              <div className="flex flex-wrap gap-2">
                {dashboard.risk_zones_low_coverage.map(d => (
                  <span key={d.subject_type} className="badge bg-amber-50 text-amber-700 border border-amber-200">
                    {d.subject_type}: {d.c}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'gaps' && (
        <div className="space-y-4">
          <p className="text-sm text-surface-400">
            Выявление неизученных комбинаций «материал × процесс × условие × география».
          </p>
          <div className="flex flex-wrap gap-2">
            {GAP_PRESETS.map(p => (
              <button key={p.label} type="button" className="btn-secondary text-xs" disabled={loading}
                onClick={() => runGaps(p)}>
                {p.label}
              </button>
            ))}
          </div>
          {loading && <Loader2 className="animate-spin-slow text-brand-600" />}
          {gaps && (
            <div className="card p-5 space-y-3">
              {(gaps.ontology_gaps || [gaps]).slice(0, 3).map(g => (
                <div key={g.scenario_id || g.label} className="border-b border-surface-800 pb-3 last:border-0">
                  <h3 className="text-sm font-bold text-surface-100">{g.label}</h3>
                  <p className={clsx('text-sm mt-1', g.is_gap ? 'text-amber-600' : 'text-emerald-600')}>
                    {g.is_gap ? `⚠ Пробел (${g.gap_severity})` : '✓ Данные найдены'}
                    {g.full_overlap_facts != null && ` · совпадений: ${g.full_overlap_facts}`}
                  </p>
                  {g.recommendation && (
                    <p className="text-xs text-surface-400 mt-2">{g.recommendation}</p>
                  )}
                  {g.sample_facts?.length > 0 && (
                    <ul className="text-xs mt-2 space-y-1 text-surface-300">
                      {g.sample_facts.slice(0, 5).map((f, i) => (
                        <li key={i}>{f.subject} → {f.object}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'review' && CAN_SYNTHESIS.has(user?.role) && (
        <form onSubmit={runReview} className="card p-4 flex gap-3">
          <input className="input flex-1" value={topic} onChange={e => setTopic(e.target.value)}
            placeholder="Тема литобзора…" />
          <button type="submit" className="btn-primary shrink-0" disabled={loading}>
            {loading ? <Loader2 size={14} className="animate-spin-slow" /> : <Sparkles size={14} />}
            Сгенерировать
          </button>
        </form>
      )}

      {review && (
        <div className="card p-5 space-y-4">
          <div className="flex gap-4 text-sm">
            <span>Уверенность: <strong>{review.confidence}</strong></span>
            <span>Источников: {review.sources_count}</span>
            <span>Verified: {review.verified_sources}</span>
          </div>
          {review.summary && <p className="text-sm text-surface-200 whitespace-pre-wrap">{review.summary}</p>}
          {review.consensus_findings?.length > 0 && (
            <div>
              <h4 className="text-xs font-bold text-surface-400 mb-2">Консенсус</h4>
              {review.consensus_findings.slice(0, 5).map((f, i) => (
                <p key={i} className="text-sm">{f.subject} → {f.object}</p>
              ))}
            </div>
          )}
          {review.disagreements?.length > 0 && (
            <div>
              <h4 className="text-xs font-bold text-amber-600 mb-2">Разногласия</h4>
              {review.disagreements.slice(0, 5).map((f, i) => (
                <p key={i} className="text-sm">{f.subject} contradicts {f.object}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'compare' && (
        <form onSubmit={runCompare} className="card p-4 space-y-3">
          <label className="label">Технологии (через запятую)</label>
          <input className="input" value={techs} onChange={e => setTechs(e.target.value)} />
          <button type="submit" className="btn-primary" disabled={loading}>Сравнить</button>
        </form>
      )}

      {compare?.comparison && (
        <div className="card p-5 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-surface-400 border-b">
                <th className="pb-2">Технология</th>
                <th className="pb-2">Фактов</th>
                <th className="pb-2">Verified</th>
                <th className="pb-2">Географии</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(compare.comparison).map(([name, t]) => (
                <tr key={name} className="border-b border-surface-800">
                  <td className="py-2 font-medium">{name}</td>
                  <td className="py-2">{t.facts_count ?? '—'}</td>
                  <td className="py-2">{t.verified_count ?? '—'}</td>
                  <td className="py-2 text-xs">{(t.geographies || []).join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {compare.recommendation && (
            <p className="text-xs text-surface-400 mt-3">{compare.recommendation}</p>
          )}
        </div>
      )}

      {tab === 'export' && CAN_EXPORT.has(user?.role) && (
        <div className="card p-5 space-y-3">
          <input className="input" value={topic} onChange={e => setTopic(e.target.value)} placeholder="Тема отчёта" />
          <div className="flex gap-2">
            {['md', 'pdf', 'jsonld'].map(fmt => (
              <button key={fmt} type="button" className="btn-secondary text-xs uppercase" onClick={() => doExport(fmt)}>
                {fmt}
              </button>
            ))}
          </div>
          {exportMsg && <p className="text-sm text-emerald-600">{exportMsg}</p>}
        </div>
      )}
    </div>
  )
}
