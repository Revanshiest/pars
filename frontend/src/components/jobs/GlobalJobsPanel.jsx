import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronDown, ChevronUp, Loader2, CheckCircle, AlertCircle, Clock, Terminal, ExternalLink,
} from 'lucide-react'
import clsx from 'clsx'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import { useAuth } from '../../context/AuthContext'
import { useJobs } from '../../context/JobsContext'
import { api } from '../../api/client'

const STATUS = {
  completed: { icon: CheckCircle, color: 'text-emerald-600' },
  running: { icon: Loader2, color: 'text-brand-600', spin: true },
  pending: { icon: Clock, color: 'text-surface-400' },
  failed: { icon: AlertCircle, color: 'text-red-500' },
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

function JobLogs({ auth, jobId }) {
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
          return [...prev, ...batch.filter(l => !ids.has(l.id))].slice(-200)
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
    <div className="border-t border-brand-100 bg-surface-50 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-surface-700 bg-white text-xs text-surface-400">
        <Terminal size={13} />
        <span className="font-semibold">Лог</span>
        <span className="ml-auto">{logs.length} записей</span>
      </div>
      <div className="max-h-40 overflow-y-auto p-2 font-mono text-[10px] leading-relaxed space-y-0.5">
        {logs.length === 0 && <div className="text-surface-400 px-1">Ожидание логов…</div>}
        {logs.map(line => (
          <div key={line.id} className={clsx('log-line-' + (line.level || 'info'))}>
            <span className="text-surface-500 select-none">
              {format(new Date(line.created_at), 'HH:mm:ss', { locale: ru })}
            </span>
            {line.stage && <span className="text-brand-500 ml-1.5">[{line.stage}]</span>}
            <span className="ml-1.5">{line.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

export default function GlobalJobsPanel() {
  const { auth } = useAuth()
  const { activeJobs } = useJobs()
  const [collapsed, setCollapsed] = useState(false)
  const [selectedId, setSelectedId] = useState(null)

  useEffect(() => {
    if (selectedId && !activeJobs.some(j => j.id === selectedId)) {
      setSelectedId(null)
    }
  }, [activeJobs, selectedId])

  if (activeJobs.length === 0) return null

  const selectedJob = activeJobs.find(j => j.id === selectedId)

  return (
    <div className="fixed bottom-4 right-4 z-50 w-96 max-w-[calc(100vw-2rem)] animate-fade-in">
      <div className="card border-brand-200 shadow-card-hover accent-glow overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2.5 bg-brand-50 border-b border-brand-100">
          <button
            type="button"
            onClick={() => setCollapsed(v => !v)}
            className="flex items-center gap-2 flex-1 min-w-0 text-left"
          >
            <Loader2 size={14} className="text-brand-600 animate-spin-slow shrink-0" />
            <span className="text-xs font-semibold text-brand-700 truncate">
              Активных задач: {activeJobs.length}
            </span>
            {collapsed ? <ChevronUp size={14} className="shrink-0" /> : <ChevronDown size={14} className="shrink-0" />}
          </button>
          <Link
            to="/jobs"
            className="flex items-center gap-1 text-[10px] font-semibold text-brand-600 hover:text-brand-700 shrink-0"
            title="Все задачи"
          >
            <ExternalLink size={12} />
            <span>Задачи</span>
          </Link>
        </div>

        {!collapsed && (
          <>
            <div className="max-h-64 overflow-y-auto p-2 space-y-2">
              {activeJobs.map(job => {
                const cfg = STATUS[job.status] || STATUS.pending
                const Icon = cfg.icon
                const progress = pct(job)
                const selected = job.id === selectedId
                return (
                  <button
                    key={job.id}
                    type="button"
                    onClick={() => setSelectedId(prev => (prev === job.id ? null : job.id))}
                    className={clsx(
                      'w-full rounded-xl border bg-white p-3 text-left transition-all',
                      selected
                        ? 'border-brand-400 ring-2 ring-brand-200 shadow-sm'
                        : 'border-surface-700 hover:border-brand-300',
                    )}
                  >
                    <div className="flex items-start gap-2">
                      <Icon size={14} className={clsx('mt-0.5 shrink-0', cfg.color, cfg.spin && 'animate-spin-slow')} />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold text-surface-100 truncate">{job.filename}</div>
                        <div className="text-[10px] text-surface-400 mt-0.5 truncate">
                          {format(new Date(job.created_at), 'HH:mm', { locale: ru })}
                          {job.message && ` · ${job.message}`}
                        </div>
                        <div className="mt-1.5 h-1 bg-surface-800 rounded-full overflow-hidden">
                          <div className="h-full bg-brand-600 transition-all" style={{ width: `${progress}%` }} />
                        </div>
                        <div className="flex justify-between text-[10px] text-surface-400 mt-0.5">
                          <span>{job.stage || job.status}</span>
                          <span className="font-bold text-brand-600">{progress}%</span>
                        </div>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>

            {selectedJob && auth && (
              <JobLogs auth={auth} jobId={selectedJob.id} />
            )}
          </>
        )}
      </div>
    </div>
  )
}
