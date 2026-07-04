import { useCallback, useEffect, useState } from 'react'
import { Bell, Check, Loader2, Plus, Trash2, X } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

export default function NotificationsBell() {
  const { auth, user } = useAuth()
  const canSubscribe = ['researcher', 'analyst', 'project_manager', 'admin'].includes(user?.role)
  const [open, setOpen] = useState(false)
  const [panel, setPanel] = useState('notifications')
  const [items, setItems] = useState([])
  const [subs, setSubs] = useState([])
  const [loading, setLoading] = useState(false)
  const [newTopic, setNewTopic] = useState('')
  const [busy, setBusy] = useState(false)

  const loadNotifications = useCallback(async () => {
    try {
      const data = await api.listNotifications(auth, true)
      setItems(Array.isArray(data) ? data : data?.notifications || [])
    } catch {
      setItems([])
    }
  }, [auth])

  const loadSubs = useCallback(async () => {
    if (!canSubscribe) return
    try {
      const data = await api.listSubscriptions(auth)
      setSubs(Array.isArray(data) ? data : [])
    } catch {
      setSubs([])
    }
  }, [auth, canSubscribe])

  const load = useCallback(async () => {
    setLoading(true)
    await Promise.all([loadNotifications(), loadSubs()])
    setLoading(false)
  }, [loadNotifications, loadSubs])

  useEffect(() => {
    load()
    const t = setInterval(loadNotifications, 60000)
    return () => clearInterval(t)
  }, [load, loadNotifications])

  const markRead = async (id) => {
    try {
      await api.markNotificationRead(auth, id)
      setItems(prev => prev.filter(n => n.id !== id))
    } catch { /* ignore */ }
  }

  const addSub = async (e) => {
    e.preventDefault()
    const topic = newTopic.trim()
    if (topic.length < 2) return
    setBusy(true)
    try {
      await api.subscribe(auth, topic)
      setNewTopic('')
      await loadSubs()
    } catch { /* ignore */ }
    finally {
      setBusy(false)
    }
  }

  const removeSub = async (id) => {
    setBusy(true)
    try {
      await api.unsubscribe(auth, id)
      setSubs(prev => prev.filter(s => s.id !== id))
    } catch { /* ignore */ }
    finally {
      setBusy(false)
    }
  }

  const unread = items.length

  return (
    <div className="relative">
      <button
        type="button"
        className="btn-ghost relative p-2"
        onClick={() => { setOpen(v => !v); if (!open) load() }}
        title="Уведомления и подписки"
      >
        <Bell size={18} />
        {unread > 0 && (
          <span className="absolute top-1 right-1 w-4 h-4 rounded-full bg-brand-600 text-white text-[9px] font-bold flex items-center justify-center">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <>
          <button type="button" className="fixed inset-0 z-40" aria-label="Закрыть" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-2 w-96 max-h-[28rem] overflow-hidden card shadow-lg z-50 flex flex-col">
            <div className="flex items-center justify-between px-3 py-2 border-b border-surface-700">
              <div className="flex gap-1">
                {[
                  ['notifications', 'Уведомления'],
                  canSubscribe && ['subscriptions', 'Подписки'],
                ].filter(Boolean).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setPanel(id)}
                    className={clsx(
                      'px-2 py-1 rounded text-[10px] font-semibold',
                      panel === id ? 'bg-brand-600 text-white' : 'text-surface-400 hover:text-surface-200',
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <button type="button" className="btn-ghost p-1" onClick={() => setOpen(false)}>
                <X size={14} />
              </button>
            </div>

            <div className="overflow-y-auto flex-1 p-2 space-y-1">
              {loading && <Loader2 size={16} className="animate-spin-slow mx-auto text-brand-600 my-4" />}

              {panel === 'notifications' && !loading && (
                <>
                  {items.length === 0 && (
                    <p className="text-xs text-surface-400 px-2 py-6 text-center">Новых уведомлений нет</p>
                  )}
                  {items.map(n => (
                    <div key={n.id} className="rounded-lg border border-surface-800 p-3 text-xs">
                      <p className="font-semibold text-surface-100">{n.title}</p>
                      <p className="text-surface-400 mt-1 leading-relaxed">{n.body}</p>
                      <button type="button" className="btn-ghost text-[10px] mt-2 gap-1" onClick={() => markRead(n.id)}>
                        <Check size={12} /> Прочитано
                      </button>
                    </div>
                  ))}
                </>
              )}

              {panel === 'subscriptions' && canSubscribe && !loading && (
                <>
                  <form onSubmit={addSub} className="flex gap-2 p-1 mb-2">
                    <input
                      className="input flex-1 text-xs py-1.5"
                      value={newTopic}
                      onChange={e => setNewTopic(e.target.value)}
                      placeholder="Тема: никель, обессоливание…"
                    />
                    <button type="submit" className="btn-primary px-2 shrink-0" disabled={busy || newTopic.trim().length < 2}>
                      {busy ? <Loader2 size={12} className="animate-spin-slow" /> : <Plus size={12} />}
                    </button>
                  </form>
                  <p className="text-[10px] text-surface-500 px-1 mb-2">
                    Оповещение при загрузке документов по совпадающей теме
                  </p>
                  {subs.length === 0 && (
                    <p className="text-xs text-surface-400 px-2 py-4 text-center">Подписок пока нет</p>
                  )}
                  {subs.map(s => (
                    <div key={s.id} className="flex items-center gap-2 rounded-lg border border-surface-800 px-3 py-2 text-xs">
                      <span className="flex-1 font-medium text-surface-200 truncate">{s.topic}</span>
                      <button type="button" className="btn-ghost p-1 text-red-500" onClick={() => removeSub(s.id)} disabled={busy}>
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
