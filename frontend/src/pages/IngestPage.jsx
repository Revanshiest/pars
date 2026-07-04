import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Upload, FolderOpen, Play, Loader2, CheckCircle, Clock, AlertCircle,
  ChevronDown, ChevronRight, FileText, RefreshCw, Terminal, FileJson, Link2,
} from 'lucide-react'
import clsx from 'clsx'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import { useAuth } from '../context/AuthContext'
import { useJobs } from '../context/JobsContext'
import { api } from '../api/client'

const JOB_TYPE_LABELS = {
  batch: { label: 'Пакет LLM', className: 'bg-brand-100 text-brand-700 border-brand-200' },
  batch_pairs: { label: 'Пакет пар', className: 'bg-violet-100 text-violet-700 border-violet-200' },
  import_pair: { label: 'Doc + JSON', className: 'bg-violet-100 text-violet-700 border-violet-200' },
}

const STATUS = {
  completed: { label: 'Готово', icon: CheckCircle, color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200' },
  running:   { label: 'Обработка', icon: Loader2, color: 'text-brand-600', bg: 'bg-brand-50 border-brand-200', spin: true },
  pending:   { label: 'Очередь', icon: Clock, color: 'text-surface-400', bg: 'bg-surface-900 border-surface-700' },
  failed:    { label: 'Ошибка', icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-50 border-red-200' },
}

function pct(job) {
  const isBatch = job.job_type === 'batch' || job.job_type === 'batch_pairs'
  if (isBatch && job.files_total > 0) {
    return Math.round(((job.files_done + job.files_failed) / job.files_total) * 100)
  }
  if (job.progress_total > 0) {
    return Math.round((job.progress_current / job.progress_total) * 100)
  }
  return job.status === 'completed' ? 100 : 0
}

function LogPanel({ auth, jobId }) {
  const [logs, setLogs] = useState([])
  const sinceRef = useRef(0)
  const bottomRef = useRef(null)

  useEffect(() => {
    sinceRef.current = 0
    setLogs([])
  }, [jobId])

  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      try {
        const batch = await api.getJobLogs(auth, jobId, sinceRef.current)
        if (cancelled || !batch.length) return
        setLogs(prev => {
          const ids = new Set(prev.map(l => l.id))
          return [...prev, ...batch.filter(l => !ids.has(l.id))].slice(-500)
        })
        sinceRef.current = batch[batch.length - 1].id
      } catch { /* ignore */ }
    }
    poll()
    const t = setInterval(poll, 2000)
    return () => { cancelled = true; clearInterval(t) }
  }, [auth, jobId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="mt-3 rounded-xl border border-surface-700 bg-surface-50 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-surface-700 bg-white text-xs text-surface-400">
        <Terminal size={13} />
        <span className="font-semibold">Лог выполнения</span>
        <span className="ml-auto">{logs.length} записей</span>
      </div>
      <div className="max-h-64 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed space-y-0.5">
        {logs.length === 0 && <div className="text-surface-400">Ожидание логов…</div>}
        {logs.map(line => (
          <div key={line.id} className={clsx('log-line-' + (line.level || 'info'))}>
            <span className="text-surface-500 select-none">
              {format(new Date(line.created_at), 'HH:mm:ss', { locale: ru })}
            </span>
            {line.stage && <span className="text-brand-500 ml-2">[{line.stage}]</span>}
            <span className="ml-2">{line.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

function JobRow({ job, auth, expanded, onToggle, onRefresh }) {
  const cfg = STATUS[job.status] || STATUS.pending
  const Icon = cfg.icon
  const progress = pct(job)
  const isBatch = job.job_type === 'batch' || job.job_type === 'batch_pairs'
  const typeBadge = JOB_TYPE_LABELS[job.job_type]

  return (
    <div className={clsx('card border transition-all', cfg.bg)}>
      <button type="button" onClick={onToggle} className="w-full flex items-start gap-3 p-4 text-left">
        <div className="mt-0.5">
          {expanded
            ? <ChevronDown size={16} className="text-surface-400" />
            : <ChevronRight size={16} className="text-surface-400" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {isBatch
              ? <FolderOpen size={14} className="text-brand-600 shrink-0" />
              : <FileText size={14} className="text-surface-400 shrink-0" />}
            <span className="text-sm font-semibold text-surface-100 truncate">{job.filename}</span>
            {typeBadge && (
              <span className={clsx('badge border', typeBadge.className)}>{typeBadge.label}</span>
            )}
          </div>
          <div className="text-xs text-surface-400 mt-1 flex flex-wrap gap-x-2">
            <span>{format(new Date(job.created_at), 'dd MMM yyyy HH:mm', { locale: ru })}</span>
            {job.created_by && <span>· {job.created_by}</span>}
            {isBatch && (
              <span>· {job.files_done}/{job.files_total}
                {job.files_failed > 0 && <span className="text-red-500"> ({job.files_failed} ошибок)</span>}
              </span>
            )}
            {job.message && !expanded && <span className="text-surface-300 truncate">· {job.message}</span>}
          </div>
          {(job.status === 'running' || job.status === 'pending' || isBatch) && (
            <div className="mt-2 h-1.5 bg-surface-800 rounded-full overflow-hidden max-w-md">
              <div className="h-full bg-brand-600 rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Icon size={16} className={clsx(cfg.color, cfg.spin && 'animate-spin-slow')} />
          <span className={clsx('text-xs font-medium', cfg.color)}>{cfg.label}</span>
          <span className="text-xs font-bold text-brand-600">{progress}%</span>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-surface-700/50">
          {job.folder_path && <p className="text-xs text-surface-400 mt-3 font-mono">{job.folder_path}</p>}
          {job.error && <p className="text-sm text-red-500 mt-2">{job.error}</p>}
          {job.stage && <p className="text-xs text-surface-400 mt-2">Этап: <strong>{job.stage}</strong></p>}
          <LogPanel auth={auth} jobId={job.id} />
          <button type="button" className="btn-ghost text-xs mt-2" onClick={onRefresh}>
            <RefreshCw size={12} /> Обновить статус
          </button>
        </div>
      )}
    </div>
  )
}

function ScenarioHeader({ n, title, desc }) {
  return (
    <div className="mb-3">
      <h3 className="section-title text-sm flex items-center gap-2">
        <span className="w-6 h-6 rounded-full bg-brand-100 text-brand-700 text-xs font-bold flex items-center justify-center">{n}</span>
        {title}
      </h3>
      {desc && <p className="text-xs text-surface-400 mt-1 ml-8">{desc}</p>}
    </div>
  )
}

export default function IngestPage() {
  const { auth, user } = useAuth()
  const { jobs, expanded, expandJob, toggleExpanded, refreshJobs, error: jobsError } = useJobs()
  const [folders, setFolders] = useState([])
  const [folderPath, setFolderPath] = useState('data/inbox')
  const [folderMode, setFolderMode] = useState('full')
  const [folderFiles, setFolderFiles] = useState([])
  const [folderName, setFolderName] = useState('')
  const [extractor, setExtractor] = useState('auto')
  const [recursive, setRecursive] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [pairDoc, setPairDoc] = useState(null)
  const [pairJson, setPairJson] = useState(null)

  const fileRef = useRef(null)
  const folderRef = useRef(null)
  const pairsRef = useRef(null)
  const pairDocRef = useRef(null)
  const pairJsonRef = useRef(null)

  const loadFolders = useCallback(async () => {
    try {
      const res = await api.listFolders(auth)
      setFolders(res.folders || [])
    } catch { /* optional */ }
  }, [auth])

  useEffect(() => {
    loadFolders()
  }, [loadFolders])

  const visibleJobs = showAll
    ? jobs
    : jobs.filter(j => j.status === 'running' || j.status === 'pending' || expanded[j.id])

  const onFolderPick = (fileList) => {
    const files = [...fileList]
    setFolderFiles(files)
    const first = files[0]
    const rel = first?.webkitRelativePath || first?.name || ''
    const root = rel.includes('/') ? rel.split('/')[0] : rel || 'папка'
    setFolderName(root)
  }

  const uploadFolder = async () => {
    if (!folderFiles.length) {
      setError('Выберите папку')
      return
    }
    setLoading(true)
    setError('')
    try {
      const job = await api.uploadFolder(
        auth,
        folderFiles,
        folderMode,
        folderMode === 'full' && extractor !== 'auto' ? extractor : undefined,
      )
      expandJob(job.id)
      await refreshJobs()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const startFolder = async () => {
    setLoading(true)
    setError('')
    try {
      const job = await api.ingestFolder(
        auth, folderPath,
        folderMode === 'full' && extractor !== 'auto' ? extractor : undefined,
        recursive,
        folderMode,
      )
      expandJob(job.id)
      await refreshJobs()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const uploadFiles = async (files) => {
    setLoading(true)
    setError('')
    try {
      for (const file of files) {
        const job = await api.uploadFile(auth, file, extractor !== 'auto' ? extractor : undefined)
        expandJob(job.id)
      }
      await refreshJobs()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const submitPair = async () => {
    if (!pairDoc || !pairJson) {
      setError('Выберите документ и JSON')
      return
    }
    setLoading(true)
    setError('')
    try {
      const job = await api.importPair(auth, pairDoc, pairJson)
      expandJob(job.id)
      setPairDoc(null)
      setPairJson(null)
      await refreshJobs()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const uploadPairsBatch = async (files) => {
    setLoading(true)
    setError('')
    try {
      const job = await api.importPairs(auth, files)
      expandJob(job.id)
      await refreshJobs()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const active = jobs.filter(j => j.status === 'running' || j.status === 'pending')
  const canUpload = user?.role !== 'external_partner'

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Активных', value: active.length, color: 'text-brand-600' },
          { label: 'Всего в списке', value: jobs.length, color: 'text-surface-100' },
          { label: 'Завершено', value: jobs.filter(j => j.status === 'completed').length, color: 'text-emerald-600' },
          { label: 'Ошибок', value: jobs.filter(j => j.status === 'failed').length, color: 'text-red-500' },
        ].map(s => (
          <div key={s.label} className="card p-3 text-center">
            <div className={clsx('text-2xl font-bold', s.color)}>{s.value}</div>
            <div className="text-xs text-surface-400 mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      {canUpload && (
        <div className="space-y-5">
          {/* 1 — один документ, полный пайплайн */}
          <div className="card p-5">
            <ScenarioHeader
              n={1}
              title="Один документ — полная обработка"
              desc="LLM извлекает тройки → SQLite + Neo4j + эмбеддинги в Qdrant"
            />
            <div
              className="border-2 border-dashed border-surface-700 rounded-xl p-6 text-center hover:border-brand-300 hover:bg-brand-50/40 transition-all cursor-pointer"
              onClick={() => fileRef.current?.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); uploadFiles([...e.dataTransfer.files]) }}
            >
              <input ref={fileRef} type="file" multiple accept=".pdf,.md,.txt,.docx,.xlsx,.xls" className="hidden"
                onChange={e => uploadFiles([...e.target.files])} />
              <Upload size={22} className="mx-auto text-brand-500 mb-2" />
              <p className="text-sm font-medium">PDF, DOCX, MD, TXT, XLSX</p>
            </div>
            <div className="mt-3 max-w-xs">
              <label className="label mb-1 block text-xs">Экстрактор</label>
              <select className="input text-sm" value={extractor} onChange={e => setExtractor(e.target.value)}>
                <option value="auto">auto</option>
                <option value="ollama">ollama</option>
                <option value="yandex">yandex</option>
              </select>
            </div>
          </div>

          {/* 2 — папка из браузера */}
          <div className="card p-5 space-y-4">
            <ScenarioHeader
              n={2}
              title="Папка — пакетная обработка"
              desc="Выберите папку на компьютере. Режим «пары» — report.pdf + report_extracted.json"
            />
            <div
              className="border-2 border-dashed border-surface-700 rounded-xl p-6 text-center hover:border-brand-300 hover:bg-brand-50/40 transition-all cursor-pointer"
              onClick={() => folderRef.current?.click()}
            >
              <input
                ref={folderRef}
                type="file"
                webkitdirectory=""
                directory=""
                multiple
                className="hidden"
                onChange={e => onFolderPick(e.target.files || [])}
              />
              <FolderOpen size={22} className="mx-auto text-brand-500 mb-2" />
              <p className="text-sm font-medium">
                {folderName ? folderName : 'Выберите папку…'}
              </p>
              {folderFiles.length > 0 && (
                <p className="text-xs text-surface-400 mt-1">{folderFiles.length} файлов</p>
              )}
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="label mb-1.5 block">Режим</label>
                <select className="input text-sm" value={folderMode} onChange={e => setFolderMode(e.target.value)}>
                  <option value="full">Полный LLM-пайплайн</option>
                  <option value="import_pairs">Doc + JSON (готовые тройки)</option>
                </select>
              </div>
              {folderMode === 'full' && (
                <div>
                  <label className="label mb-1.5 block">Экстрактор</label>
                  <select className="input text-sm" value={extractor} onChange={e => setExtractor(e.target.value)}>
                    <option value="auto">auto</option>
                    <option value="ollama">ollama</option>
                    <option value="yandex">yandex</option>
                  </select>
                </div>
              )}
            </div>
            <button type="button" className="btn-primary" onClick={uploadFolder} disabled={loading || !folderFiles.length}>
              {loading ? <Loader2 size={14} className="animate-spin-slow" /> : <Play size={14} />}
              Загрузить и запустить
            </button>

            <div className="border-t border-surface-700 pt-3">
              <button
                type="button"
                className="btn-ghost text-xs"
                onClick={() => setShowAdvanced(v => !v)}
              >
                {showAdvanced ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                Расширенно: путь на сервере
              </button>
              {showAdvanced && (
                <div className="mt-3 space-y-3">
                  <div>
                    <label className="label mb-1.5 block">Путь к папке на сервере</label>
                    <input className="input font-mono text-sm" value={folderPath} onChange={e => setFolderPath(e.target.value)} list="folder-list" />
                    <datalist id="folder-list">
                      {folders.map(f => <option key={f.path} value={f.path}>{f.name}</option>)}
                    </datalist>
                  </div>
                  <label className="flex items-center gap-2 text-sm text-surface-300 cursor-pointer">
                    <input type="checkbox" checked={recursive} onChange={e => setRecursive(e.target.checked)} className="rounded" />
                    Рекурсивно
                  </label>
                  <button type="button" className="btn-secondary text-xs" onClick={startFolder} disabled={loading || !folderPath}>
                    Запустить на сервере
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* 3 — одна пара doc + json */}
          <div className="card p-5 space-y-4">
            <ScenarioHeader
              n={3}
              title="Одна пара: документ + JSON"
              desc="JSON → БД (тройки, Neo4j). Документ → только эмбеддинги в Qdrant"
            />
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="label mb-1.5 block">Документ (PDF/DOCX/MD/TXT)</label>
                <button type="button" className="input w-full text-left text-sm truncate" onClick={() => pairDocRef.current?.click()}>
                  {pairDoc?.name || 'Выбрать файл…'}
                </button>
                <input ref={pairDocRef} type="file" accept=".pdf,.md,.txt,.docx" className="hidden"
                  onChange={e => setPairDoc(e.target.files?.[0] || null)} />
              </div>
              <div>
                <label className="label mb-1.5 block">JSON с triples</label>
                <button type="button" className="input w-full text-left text-sm truncate" onClick={() => pairJsonRef.current?.click()}>
                  {pairJson?.name || 'Выбрать файл…'}
                </button>
                <input ref={pairJsonRef} type="file" accept=".json,application/json" className="hidden"
                  onChange={e => setPairJson(e.target.files?.[0] || null)} />
              </div>
            </div>
            <p className="text-xs text-surface-400">
              Имена должны совпадать: <code className="font-mono">report.pdf</code> +{' '}
              <code className="font-mono">report_extracted.json</code>
            </p>
            <button type="button" className="btn-primary" onClick={submitPair} disabled={loading || !pairDoc || !pairJson}>
              {loading ? <Loader2 size={14} className="animate-spin-slow" /> : <Link2 size={14} />}
              Загрузить пару
            </button>
          </div>

          {/* 4 — много пар через upload */}
          <div className="card p-5">
            <ScenarioHeader
              n={4}
              title="Много пар: документы + JSON"
              desc="Загрузите все файлы сразу — пары сопоставятся автоматически по имени"
            />
            <div
              className="border-2 border-dashed border-violet-200 rounded-xl p-6 text-center hover:border-violet-400 hover:bg-violet-50/30 transition-all cursor-pointer"
              onClick={() => pairsRef.current?.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); uploadPairsBatch([...e.dataTransfer.files]) }}
            >
              <input ref={pairsRef} type="file" multiple
                accept=".pdf,.md,.txt,.docx,.json,application/json" className="hidden"
                onChange={e => uploadPairsBatch([...e.target.files])} />
              <FileJson size={22} className="mx-auto text-violet-500 mb-2" />
              <p className="text-sm font-medium">Перетащите doc + json файлы</p>
              <p className="text-xs text-surface-400 mt-1">report.pdf, report_extracted.json, paper.docx, paper.json …</p>
            </div>
          </div>
        </div>
      )}

      {jobsError && (
        <div className="card p-4 border-amber-200 bg-amber-50 text-amber-700 text-sm">{jobsError}</div>
      )}

      {error && (
        <div className="card p-4 border-red-200 bg-red-50 text-red-600 text-sm">{error}</div>
      )}

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="section-title text-sm">{showAll ? 'Все задачи' : 'Активные работы'}</h3>
          <div className="flex gap-2">
            <button type="button" className="btn-secondary text-xs" onClick={() => setShowAll(v => !v)}>
              {showAll ? 'Только активные' : 'Показать все'}
            </button>
            <button type="button" className="btn-ghost text-xs" onClick={refreshJobs}>
              <RefreshCw size={13} /> Обновить
            </button>
          </div>
        </div>

        {visibleJobs.length === 0 && (
          <div className="card p-8 text-center text-surface-400 text-sm">
            Нет задач. Выберите один из сценариев выше.
          </div>
        )}

        <div className="space-y-2">
          {visibleJobs.map(job => (
            <JobRow
              key={job.id}
              job={job}
              auth={auth}
              expanded={!!expanded[job.id]}
              onToggle={() => toggleExpanded(job.id)}
              onRefresh={refreshJobs}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
