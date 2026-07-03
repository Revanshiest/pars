import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Upload, FolderOpen, Play, Loader2, CheckCircle, Clock, AlertCircle,
  ChevronDown, ChevronRight, FileText, RefreshCw, Terminal,
} from 'lucide-react'
import clsx from 'clsx'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

const STATUS = {
  completed: { label: 'Готово', icon: CheckCircle, color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200' },
  running:   { label: 'Обработка', icon: Loader2, color: 'text-brand-600', bg: 'bg-brand-50 border-brand-200', spin: true },
  pending:   { label: 'Очередь', icon: Clock, color: 'text-surface-400', bg: 'bg-surface-900 border-surface-700' },
  failed:    { label: 'Ошибка', icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-50 border-red-200' },
}

function pct(job) {
  if (job.job_type === 'batch' && job.files_total > 0) {
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
          const merged = [...prev, ...batch.filter(l => !ids.has(l.id))]
          return merged.slice(-500)
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
        {logs.length === 0 && (
          <div className="text-surface-400">Ожидание логов…</div>
        )}
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
  const isBatch = job.job_type === 'batch'

  return (
    <div className={clsx('card border transition-all', cfg.bg)}>
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-start gap-3 p-4 text-left"
      >
        <div className="mt-0.5">
          {expanded ? <ChevronDown size={16} className="text-surface-400" /> : <ChevronRight size={16} className="text-surface-400" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {isBatch ? <FolderOpen size={14} className="text-brand-600 shrink-0" /> : <FileText size={14} className="text-surface-400 shrink-0" />}
            <span className="text-sm font-semibold text-surface-100 truncate">{job.filename}</span>
            {isBatch && (
              <span className="badge bg-brand-100 text-brand-700 border border-brand-200">Пакет</span>
            )}
          </div>
          <div className="text-xs text-surface-400 mt-1 flex flex-wrap gap-x-2">
            <span>{format(new Date(job.created_at), 'dd MMM yyyy HH:mm', { locale: ru })}</span>
            {job.created_by && <span>· {job.created_by}</span>}
            {isBatch && (
              <span>· {job.files_done}/{job.files_total} файлов
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
          {job.folder_path && (
            <p className="text-xs text-surface-400 mt-3 font-mono">{job.folder_path}</p>
          )}
          {job.error && (
            <p className="text-sm text-red-500 mt-2">{job.error}</p>
          )}
          {job.stage && (
            <p className="text-xs text-surface-400 mt-2">Этап: <strong>{job.stage}</strong></p>
          )}
          <LogPanel auth={auth} jobId={job.id} />
          <div className="mt-2 flex gap-2">
            <button type="button" className="btn-ghost text-xs" onClick={onRefresh}>
              <RefreshCw size={12} /> Обновить статус
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function IngestPage() {
  const { auth, user } = useAuth()
  const [jobs, setJobs] = useState([])
  const [folders, setFolders] = useState([])
  const [folderPath, setFolderPath] = useState('data/inbox')
  const [extractor, setExtractor] = useState('auto')
  const [recursive, setRecursive] = useState(false)
  const [expanded, setExpanded] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showAll, setShowAll] = useState(false)
  const fileRef = useRef(null)

  const loadJobs = useCallback(async () => {
    try {
      const list = await api.listJobs(auth, { active: !showAll, limit: 100 })
      setJobs(list)
    } catch (e) {
      setError(e.message)
    }
  }, [auth, showAll])

  const loadFolders = useCallback(async () => {
    try {
      const res = await api.listFolders(auth)
      setFolders(res.folders || [])
      if (res.folders?.length && !folderPath) {
        setFolderPath(res.folders[0].path)
      }
    } catch { /* optional */ }
  }, [auth, folderPath])

  useEffect(() => {
    loadJobs()
    loadFolders()
    const t = setInterval(loadJobs, 3000)
    return () => clearInterval(t)
  }, [loadJobs, loadFolders])

  const startFolder = async () => {
    setLoading(true)
    setError('')
    try {
      const job = await api.ingestFolder(auth, folderPath, extractor, recursive)
      setExpanded(prev => ({ ...prev, [job.id]: true }))
      await loadJobs()
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
        setExpanded(prev => ({ ...prev, [job.id]: true }))
      }
      await loadJobs()
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
      {/* Stats */}
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
        <>
          {/* Folder ingest */}
          <div className="card p-5 space-y-4">
            <h3 className="section-title text-sm flex items-center gap-2">
              <FolderOpen size={16} className="text-brand-600" />
              Обработка папки на сервере
            </h3>
            <p className="text-xs text-surface-400">
              Укажите путь внутри <code className="font-mono bg-surface-900 px-1 rounded">data/inbox</code> или{' '}
              <code className="font-mono bg-surface-900 px-1 rounded">data/uploads</code>.
              Все пользователи видят прогресс и логи активных задач.
            </p>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="label mb-1.5 block">Путь к папке</label>
                <input className="input font-mono text-sm" value={folderPath} onChange={e => setFolderPath(e.target.value)} list="folder-list" />
                <datalist id="folder-list">
                  {folders.map(f => (
                    <option key={f.path} value={f.path}>{f.name}</option>
                  ))}
                </datalist>
              </div>
              <div>
                <label className="label mb-1.5 block">Экстрактор</label>
                <select className="input text-sm" value={extractor} onChange={e => setExtractor(e.target.value)}>
                  <option value="auto">auto</option>
                  <option value="ollama">ollama</option>
                  <option value="yandex">yandex</option>
                </select>
              </div>
            </div>
            <div className="flex items-center gap-4 flex-wrap">
              <label className="flex items-center gap-2 text-sm text-surface-300 cursor-pointer">
                <input type="checkbox" checked={recursive} onChange={e => setRecursive(e.target.checked)} className="rounded" />
                Рекурсивно (подпапки)
              </label>
              <button type="button" className="btn-primary" onClick={startFolder} disabled={loading || !folderPath}>
                {loading ? <Loader2 size={14} className="animate-spin-slow" /> : <Play size={14} />}
                Запустить обработку папки
              </button>
            </div>
          </div>

          {/* File upload */}
          <div
            className="border-2 border-dashed border-surface-700 rounded-2xl p-8 text-center hover:border-brand-300 hover:bg-brand-50/40 transition-all cursor-pointer"
            onClick={() => fileRef.current?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); uploadFiles([...e.dataTransfer.files]) }}
          >
            <input ref={fileRef} type="file" multiple accept=".pdf,.md,.txt,.docx,.xlsx,.xls" className="hidden"
              onChange={e => uploadFiles([...e.target.files])} />
            <div className="w-14 h-14 mx-auto bg-brand-50 border border-brand-100 rounded-2xl flex items-center justify-center mb-3">
              <Upload size={24} className="text-brand-500" />
            </div>
            <p className="text-sm font-semibold text-surface-200">Загрузить файлы</p>
            <p className="text-xs text-surface-400 mt-1">PDF, DOCX, MD, TXT, XLSX</p>
          </div>
        </>
      )}

      {error && (
        <div className="card p-4 border-red-200 bg-red-50 text-red-600 text-sm">{error}</div>
      )}

      {/* Jobs list */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="section-title text-sm">
            {showAll ? 'Все задачи' : 'Активные работы'}
          </h3>
          <div className="flex gap-2">
            <button type="button" className="btn-secondary text-xs" onClick={() => setShowAll(v => !v)}>
              {showAll ? 'Только активные' : 'Показать все'}
            </button>
            <button type="button" className="btn-ghost text-xs" onClick={loadJobs}>
              <RefreshCw size={13} /> Обновить
            </button>
          </div>
        </div>

        {jobs.length === 0 && (
          <div className="card p-8 text-center text-surface-400 text-sm">
            Нет {showAll ? '' : 'активных '}задач. Запустите обработку папки или загрузите файлы.
          </div>
        )}

        <div className="space-y-2">
          {jobs.map(job => (
            <JobRow
              key={job.id}
              job={job}
              auth={auth}
              expanded={!!expanded[job.id]}
              onToggle={() => setExpanded(prev => ({ ...prev, [job.id]: !prev[job.id] }))}
              onRefresh={loadJobs}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
