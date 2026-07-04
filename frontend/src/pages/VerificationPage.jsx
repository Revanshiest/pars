import { useCallback, useEffect, useState } from 'react'
import { CheckCircle, XCircle, Loader2, RefreshCw, ClipboardCheck } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

const CAN_VERIFY = new Set(['analyst', 'project_manager', 'admin'])

export default function VerificationPage() {
  const { auth, user } = useAuth()
  const [queue, setQueue] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(null)

  const load = useCallback(async () => {
    if (!CAN_VERIFY.has(user?.role)) return
    setLoading(true)
    setError('')
    try {
      const data = user?.role === 'analyst'
        ? await api.myVerificationQueue(auth)
        : await api.verificationQueue(auth, { limit: 50 })
      setQueue(Array.isArray(data) ? data : data?.items || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [auth, user?.role])

  useEffect(() => { load() }, [load])

  const verify = async (factId, status) => {
    setBusy(factId)
    try {
      await api.verifyFact(auth, factId, status)
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  const claim = async () => {
    setBusy('claim')
    try {
      await api.claimVerificationTasks(auth, 5)
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  if (!CAN_VERIFY.has(user?.role)) {
    return (
      <div className="card p-8 text-center text-surface-400 text-sm">
        Верификация доступна ролям analyst, project_manager, admin.
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-surface-400">
          Модель верификации: источник, уровень достоверности, статус проверки экспертом.
        </p>
        <div className="flex gap-2">
          <button type="button" className="btn-secondary text-xs" onClick={claim} disabled={busy === 'claim'}>
            Взять 5 задач
          </button>
          <button type="button" className="btn-ghost text-xs" onClick={load}>
            <RefreshCw size={13} /> Обновить
          </button>
        </div>
      </div>

      {error && <div className="card p-4 text-red-500 text-sm">{error}</div>}

      {loading ? (
        <div className="flex justify-center py-12 text-surface-400">
          <Loader2 size={20} className="animate-spin-slow" />
        </div>
      ) : queue.length === 0 ? (
        <div className="card p-8 text-center text-surface-400 text-sm">
          Очередь пуста. Загрузите документы или JSON-граф для верификации.
        </div>
      ) : (
        <div className="space-y-2">
          {queue.map(f => (
            <div key={f.id} className="card p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-surface-100">
                    {f.subject} —[{f.relation}]→ {f.object}
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2 text-xs text-surface-400">
                    <span>Источник: {f.source_document || '—'}</span>
                    {f.geography && <span>· {f.geography}</span>}
                    {f.confidence != null && <span>· conf {f.confidence}</span>}
                    <span className={clsx('badge border',
                      f.verification_status === 'verified' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                      f.verification_status === 'rejected' ? 'bg-red-50 text-red-700 border-red-200' :
                      'bg-amber-50 text-amber-700 border-amber-200')}>
                      {f.verification_status || 'pending'}
                    </span>
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button type="button" className="btn-ghost p-2 text-emerald-600" title="Подтвердить"
                    disabled={busy === f.id} onClick={() => verify(f.id, 'verified')}>
                    <CheckCircle size={16} />
                  </button>
                  <button type="button" className="btn-ghost p-2 text-red-500" title="Отклонить"
                    disabled={busy === f.id} onClick={() => verify(f.id, 'rejected')}>
                    <XCircle size={16} />
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
