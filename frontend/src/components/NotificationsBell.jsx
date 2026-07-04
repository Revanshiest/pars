import { useCallback, useEffect, useState } from 'react'
import { Bell, Check, Loader2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

export default function NotificationsBell() {
  const { auth } = useAuth()
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listNotifications(auth, true)
      setItems(Array.isArray(data) ? data : data?.notifications || [])
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [auth])

  useEffect(() => {
    load()
    const t = setInterval(load, 60000)
    return () => clearInterval(t)
  }, [load])

  const markRead = async (id) => {
    try {
      await api.markNotificationRead(auth, id)
      setItems(prev => prev.filter(n => n.id !== id))
    } catch { /* ignore */ }
  }

  const unread = items.length

  return (
    <div className="relative">
      <button
        type="button"
        className="btn-ghost relative p-2"
        onClick={() => { setOpen(v => !v); if (!open) load() }}
        title="Уведомления"
      >
        <Bell size={18} />
        {unread > 0 && (
          <span className="absolute top-1 right-1 w-4 h-4 rounded-full bg-brand-600 text-white text-[9px] font-bold flex items-center justify-center">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 max-h-96 overflow-y-auto card shadow-lg z-50 p-2 space-y-1">
          <p className="text-xs font-bold text-surface-400 px-2 py-1">Уведомления</p>
          {loading && <Loader2 size={16} className="animate-spin-slow mx-auto text-brand-600" />}
          {!loading && items.length === 0 && (
            <p className="text-xs text-surface-400 px-2 py-3 text-center">Новых уведомлений нет</p>
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
        </div>
      )}
    </div>
  )
}
