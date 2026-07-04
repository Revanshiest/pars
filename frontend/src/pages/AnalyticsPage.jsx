import { useCallback, useEffect, useState } from 'react'
import {
  BarChart3, Loader2, BookOpen, GitCompare, Download, AlertTriangle, Sparkles, RefreshCw,
  Users, Globe2,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

const CAN_SYNTHESIS = new Set(['analyst', 'project_manager', 'admin'])
const CAN_DASHBOARD = new Set(['researcher', 'analyst', 'project_manager', 'admin'])
const CAN_EXPORT = new Set(['analyst', 'project_manager', 'admin'])

export default function AnalyticsPage() {
  const { auth, user } = useAuth()
  const [tab, setTab] = useState('dashboard')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [topic, setTopic] = useState('электроэкстракция никеля')
  const [techs, setTechs] = useState('heap leaching, electrowinning, fluidized bed')
  const [dashboard, setDashboard] = useState(null)
  const [gaps, setGaps] = useState(null)
  const [gapPresets, setGapPresets] = useState([])
  const [review, setReview] = useState(null)
  const [compare, setCompare] = useState(null)
  const [practices, setPractices] = useState(null)
  const [recs, setRecs] = useState(null)
  const [exportMsg, setExportMsg] = useState('')

  useEffect(() => {
    if (tab === 'dashboard' && CAN_DASHBOARD.has(user?.role)) {
      setLoading(true)
      api.dashboard(auth)
        .then(setDashboard)
        .catch(e => setError(e.message))
        .finally(() => setLoading(false))
    }
  }, [tab, auth, user?.role])

  const runGaps = useCallback(async (preset = { auto: true }) => {
    setLoading(true)
    setError('')
    try {
      const data = preset.query
        ? await api.knowledgeGaps(auth, { query: preset.query, auto: false })
        : preset.material || preset.process || preset.climate
          ? await api.ontologyGaps(auth, { ...preset, auto: false })
          : await api.knowledgeGaps(auth, { auto: true, ...preset })
      setGaps(data)
      if (data?.suggested_presets?.length) {
        setGapPresets(data.suggested_presets)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [auth])

  useEffect(() => {
    if (tab === 'gaps' && !gaps && !loading) {
      runGaps({ auto: true })
    }
  }, [tab, gaps, loading, runGaps])

  const runReview = async (e) => {
    e.preventDefault()
    if (!CAN_SYNTHESIS.has(user?.role)) return
    setLoading(true)
    setError('')
    try {
      const data = await api.literatureReview(auth, topic, { use_llm: true })
      setReview(data)
      api.recommendations(auth, topic).then(setRecs).catch(() => {})
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

  const runPractices = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      setPractices(await api.comparePractices(auth, topic))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const runRecommendations = async (e) => {
    e?.preventDefault?.()
    setLoading(true)
    setError('')
    try {
      setRecs(await api.recommendations(auth, topic))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const doExport = async (format) => {
    setExportMsg('')
    setError('')
    try {
      const { blob, filename } = await api.exportDownload(auth, topic, format)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = filename
      a.click()
      URL.revokeObjectURL(a.href)
      setExportMsg(`Файл ${filename} скачан`)
    } catch (e) {
      setError(e.message || 'Не удалось экспортировать отчёт')
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div className="flex flex-wrap gap-2">
        {[
          CAN_DASHBOARD.has(user?.role) && ['dashboard', BarChart3, 'Дашборд'],
          ['gaps', AlertTriangle, 'Пробелы'],
          ['recs', Users, 'Рекомендации'],
          ['practices', Globe2, 'RU vs мир'],
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

      {tab === 'dashboard' && (
        <>
          {loading && !dashboard && (
            <div className="flex items-center gap-2 text-surface-400 text-sm">
              <Loader2 size={16} className="animate-spin-slow" /> Загрузка дашборда…
            </div>
          )}
          {dashboard && (
        <div className="space-y-4">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              ['Фактов', dashboard.facts_total],
              ['Проверено', dashboard.verified],
              ['На проверке', dashboard.pending_verification],
              ['Противоречий', dashboard.contradictions],
              ['Глоссарий', dashboard.glossary_terms],
            ].map(([l, v]) => (
              <div key={l} className="card p-4 text-center">
                <div className="text-2xl font-black text-brand-600">{v ?? 0}</div>
                <div className="text-xs text-surface-400">{l}</div>
              </div>
            ))}
          </div>

          {dashboard.domain_coverage && Object.keys(dashboard.domain_coverage).length > 0 && (
            <div className="card p-4">
              <h4 className="text-sm font-bold mb-3">Покрытие по направлениям R&D</h4>
              <div className="grid sm:grid-cols-2 gap-3">
                {Object.entries(dashboard.domain_coverage).map(([key, d]) => (
                  <div key={key} className="rounded-lg border border-surface-800 p-3">
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-sm font-medium text-surface-100">{d.label || key}</span>
                      <span className={clsx(
                        'text-[10px] px-2 py-0.5 rounded-full border',
                        d.risk
                          ? 'bg-amber-50 text-amber-700 border-amber-200'
                          : 'bg-emerald-50 text-emerald-700 border-emerald-200',
                      )}>
                        {Math.round((d.coverage_ratio || 0) * 100)}%
                      </span>
                    </div>
                    <p className="text-xs text-surface-400 mt-1">
                      Процессов: {d.processes_covered}/{d.processes_total} · фактов: {d.facts_matched}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {dashboard.risk_zones_low_coverage?.length > 0 && (
            <div className="card p-4">
              <h4 className="text-sm font-bold mb-2">Зоны риска (мало данных по типам сущностей)</h4>
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
        </>
      )}

      {tab === 'gaps' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-surface-400">
              Автоматический анализ комбинаций «материал × процесс × география» из графа знаний.
            </p>
            <button type="button" className="btn-secondary text-xs flex items-center gap-1" disabled={loading}
              onClick={() => runGaps({ auto: true })}>
              <RefreshCw size={12} /> Обновить
            </button>
          </div>
          {gapPresets.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {gapPresets.map((p, idx) => (
                <button key={p.label || idx} type="button" className="btn-secondary text-xs" disabled={loading}
                  onClick={() => runGaps(p)}>
                  {p.label || 'Сценарий'}
                </button>
              ))}
            </div>
          )}
          {loading && <Loader2 className="animate-spin-slow text-brand-600" />}
          {gaps && (
            <div className="card p-5 space-y-3">
              <p className="text-xs text-surface-500">
                Проанализировано сценариев: {gaps.scenarios_analyzed ?? '—'} · критических пробелов: {gaps.critical_gaps ?? 0}
              </p>
              {(gaps.ontology_gaps || []).slice(0, 8).map((g, idx) => (
                <div key={g.scenario_id || g.label || idx} className="border-b border-surface-800 pb-3 last:border-0">
                  <h3 className="text-sm font-bold text-surface-100">{g.label}</h3>
                  <p className={clsx('text-sm mt-1', g.is_gap ? 'text-amber-600' : 'text-emerald-600')}>
                    {g.is_gap ? 'Обнаружен пробел в знаниях' : 'Данные по этому сценарию есть'}
                    {g.full_overlap_facts != null && g.full_overlap_facts > 0 && ` · найдено совпадений: ${g.full_overlap_facts}`}
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

      {tab === 'recs' && (
        <form onSubmit={runRecommendations} className="card p-4 flex gap-3">
          <input className="input flex-1" value={topic} onChange={e => setTopic(e.target.value)}
            placeholder="Тема: электроэкстракция никеля…" />
          <button type="submit" className="btn-primary shrink-0" disabled={loading}>
            {loading ? <Loader2 size={14} className="animate-spin-slow" /> : 'Найти'}
          </button>
        </form>
      )}

      {recs && tab === 'recs' && (
        <div className="card p-5 space-y-4">
          {recs.experts?.length > 0 ? (
            <div>
              <h4 className="text-xs font-bold text-surface-400 mb-2">Эксперты и команды</h4>
              <div className="space-y-2">
                {recs.experts.slice(0, 8).map((ex, i) => (
                  <div key={i} className="text-sm flex justify-between gap-2 border-b border-surface-800 pb-2">
                    <span className="font-medium">{ex.name}</span>
                    <span className="text-xs text-surface-400">{ex.context || ex.source}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-surface-400">Явных экспертов в графе по теме не найдено</p>
          )}
          {recs.similar_cases?.length > 0 && (
            <div>
              <h4 className="text-xs font-bold text-surface-400 mb-2">Похожие кейсы</h4>
              {recs.similar_cases.slice(0, 6).map((c, i) => (
                <p key={i} className="text-sm">{c.subject} → {c.object}</p>
              ))}
            </div>
          )}
          {recs.suggested_actions?.length > 0 && (
            <div>
              <h4 className="text-xs font-bold text-surface-400 mb-2">Действия</h4>
              <ul className="text-sm space-y-1 list-disc pl-4 text-surface-300">
                {recs.suggested_actions.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {tab === 'practices' && (
        <form onSubmit={runPractices} className="card p-4 flex gap-3">
          <input className="input flex-1" value={topic} onChange={e => setTopic(e.target.value)}
            placeholder="Тема для сравнения практик…" />
          <button type="submit" className="btn-primary shrink-0" disabled={loading}>
            {loading ? <Loader2 size={14} className="animate-spin-slow" /> : 'Сравнить'}
          </button>
        </form>
      )}

      {practices?.comparison && tab === 'practices' && (
        <div className="card p-5 space-y-4">
          {practices.comparison?.summary && (
            <p className="text-sm text-surface-200 whitespace-pre-wrap">{practices.comparison.summary}</p>
          )}
          <div className="grid sm:grid-cols-2 gap-4">
            {practices.domestic && (
              <div className="rounded-xl border border-surface-800 p-4">
                <h4 className="text-xs font-bold text-brand-600 mb-2">{practices.domestic.label || 'RU'}</h4>
                <p className="text-sm">Фактов: {practices.domestic.verified_facts?.length ?? 0}</p>
                <ul className="text-xs mt-2 space-y-1 text-surface-400 max-h-40 overflow-y-auto">
                  {(practices.domestic.verified_facts || []).slice(0, 5).map((f, i) => (
                    <li key={i}>{f.subject} → {f.object}</li>
                  ))}
                </ul>
              </div>
            )}
            {practices.global && (
              <div className="rounded-xl border border-surface-800 p-4">
                <h4 className="text-xs font-bold text-brand-600 mb-2">{practices.global.label || 'Global'}</h4>
                <p className="text-sm">Фактов: {practices.global.verified_facts?.length ?? 0}</p>
                <ul className="text-xs mt-2 space-y-1 text-surface-400 max-h-40 overflow-y-auto">
                  {(practices.global.verified_facts || []).slice(0, 5).map((f, i) => (
                    <li key={i}>{f.subject} → {f.object}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          {practices.comparison?.ru_only_topics?.length > 0 && (
            <p className="text-xs text-surface-400">
              Только RU: {practices.comparison.ru_only_topics.slice(0, 6).join(', ')}
            </p>
          )}
          {practices.comparison?.global_only_topics?.length > 0 && (
            <p className="text-xs text-surface-400">
              Только global: {practices.comparison.global_only_topics.slice(0, 6).join(', ')}
            </p>
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
          <div className="flex gap-4 text-sm flex-wrap">
            {review.sources_count > 0 ? (
              <>
                <span>Материалов в базе: <strong>{review.sources_count}</strong></span>
                <span>Проверено экспертами: {review.verified_sources}</span>
                {review.llm_synthesized && (
                  <span className="text-surface-400">Сформировано с помощью языковой модели</span>
                )}
              </>
            ) : (
              <span className="text-surface-400">По теме пока нет материалов в базе — уверенность не рассчитывается</span>
            )}
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
                <p key={i} className="text-sm">{f.subject} — расходится с — {f.object}</p>
              ))}
            </div>
          )}
          {recs?.experts?.length > 0 && tab === 'review' && (
            <div>
              <h4 className="text-xs font-bold text-surface-400 mb-2">Эксперты по теме</h4>
              {recs.experts.slice(0, 5).map((ex, i) => (
                <p key={i} className="text-sm">{ex.name} — {ex.context || ex.source}</p>
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
        <div className="card p-5 overflow-x-auto space-y-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-surface-400 border-b">
                <th className="pb-2">Технология</th>
                <th className="pb-2">Фактов</th>
                <th className="pb-2">Проверено</th>
                <th className="pb-2">Параметры</th>
                <th className="pb-2">Географии</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(compare.comparison).map(([name, t]) => (
                <tr key={name} className="border-b border-surface-800">
                  <td className="py-2 font-medium">{name}</td>
                  <td className="py-2">{t.facts_count ?? '—'}</td>
                  <td className="py-2">{t.verified_count ?? '—'}</td>
                  <td className="py-2 text-xs align-top">
                    {t.parameters && Object.keys(t.parameters).length > 0 ? (
                      <ul className="space-y-1">
                        {Object.entries(t.parameters).slice(0, 6).map(([param, vals]) => (
                          <li key={param}>
                            <span className="font-medium text-surface-200">{param}:</span>{' '}
                            {(Array.isArray(vals) ? vals : [vals]).slice(0, 3).join('; ')}
                          </li>
                        ))}
                      </ul>
                    ) : '—'}
                  </td>
                  <td className="py-2 text-xs">{(t.geographies || []).join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {compare.recommendation && (
            <p className="text-xs text-surface-400">{compare.recommendation}</p>
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
