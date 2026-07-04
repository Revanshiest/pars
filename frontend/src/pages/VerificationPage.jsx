import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ShieldCheck, Loader2, RefreshCw, Check, X, Inbox, Network,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

export default function VerificationPage() {
  const { auth } = useAuth()
  const [queue, setQueue] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')
  const [view, setView] = useState('queue')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = view === 'my'
        ? await api.myVerificationQueue(auth)
        : await api.verificationQueue(auth, { limit: 50 })
      setQueue(Array.isArray(data) ? data : data.queue || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [auth, view])

  useEffect(() => { load() }, [load])

  const claim = async () => {
    setBusy('claim')
    try {
      await api.claimVerification(auth, 5)
      setView('my')
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  const verify = async (id, status) => {
    setBusy(id)
    try {
      await api.verifyFact(auth, id, { status, notes: '' })
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-surface-100 flex items-center gap-2">
            <ShieldCheck size={20} className="text-emerald-600" />
            Верификация знаний
          </h2>
          <p className="text-xs text-surface-400 mt-1">Проверка фактов, уровень достоверности и источники</p>
        </div>
        <div className="flex gap-2">
          <button type="button" className={clsx('btn-secondary text-xs', view === 'queue' && 'ring-2 ring-brand-500')}
            onClick={() => setView('queue')}>Очередь</button>
          <button type="button" className={clsx('btn-secondary text-xs', view === 'my' && 'ring-2 ring-brand-500')}
            onClick={() => setView('my')}>Мои задачи</button>
          <button type="button" className="btn-primary text-xs" onClick={claim} disabled={busy === 'claim'}>
            <Inbox size={13} /> Взять 5
          </button>
          <button type="button" className="btn-ghost text-xs" onClick={load} disabled={loading}>
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {error && <div className="card p-4 text-red-600 text-sm">{error}</div>}

      {loading ? (
        <div className="flex justify-center py-16 text-surface-400">
          <Loader2 size={20} className="animate-spin-slow mr-2" /> Загрузка…
        </div>
      ) : queue.length === 0 ? (
        <div className="card p-10 text-center text-surface-400 text-sm">Очередь пуста</div>
      ) : (
        <div className="space-y-3">
          {queue.map(f => (
            <div key={f.id} className="card p-4">
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-surface-100">
                    {f.subject} <span className="text-brand-600 font-mono text-xs">[{f.relation}]</span> {f.object}
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2 text-xs text-surface-400">
                    <span>{f.subject_type} → {f.object_type}</span>
                    {f.confidence != null && <span>conf {f.confidence}</span>}
                    {f.geography && <span>{f.geography}</span>}
                    {f.source_document && <span>{f.source_document}</span>}
                  </div>
                  <Link to={`/graph?entity=${encodeURIComponent(f.subject)}`}
                    className="inline-flex items-center gap-1 mt-2 text-xs text-brand-600">
                    <Network size={11} /> Граф
                  </Link>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button type="button" className="btn-primary text-xs py-1.5 px-2"
                    disabled={busy === f.id} onClick={() => verify(f.id, 'verified')}>
                    <Check size={13} />
                  </button>
                  <button type="button" className="btn-secondary text-xs py-1.5 px-2 text-red-600"
                    disabled={busy === f.id} onClick={() => verify(f.id, 'rejected')}>
                    <X size={13} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
