import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Bell, X } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../api/client'
import { useAuth } from '../../context/AuthContext'

const TITLES = {
  '/jobs': 'Обработка документов',
  '/search': 'Исследование знаний',
  '/graph': 'Граф знаний',
  '/glossary': 'Глоссарий',
  '/dashboard': 'Дашборд R&D',
  '/verify': 'Верификация',
  '/documents': 'Документы',
  '/admin': 'Управление пользователями',
}

export default function Header() {
  const { pathname } = useLocation()
  const { auth } = useAuth()
  const [health, setHealth] = useState(null)
  const [notifications, setNotifications] = useState([])
  const [showNotif, setShowNotif] = useState(false)
  const panelRef = useRef(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: 'unavailable' }))
    const t = setInterval(() => {
      api.health().then(setHealth).catch(() => setHealth({ status: 'unavailable' }))
    }, 30000)
    return () => clearInterval(t)
  }, [])

  const loadNotif = useCallback(async () => {
    try {
      const list = await api.listNotifications(auth, true)
      setNotifications(Array.isArray(list) ? list : [])
    } catch { /* ignore */ }
  }, [auth])

  useEffect(() => {
    loadNotif()
    const t = setInterval(loadNotif, 60000)
    return () => clearInterval(t)
  }, [loadNotif])

  useEffect(() => {
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) setShowNotif(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const markRead = async (id) => {
    await api.markNotificationRead(auth, id)
    loadNotif()
  }

  const ok = health?.status === 'ok' || health?.status === 'degraded'
  const unread = notifications.filter(n => !n.read).length

  return (
    <header className="h-14 shrink-0 border-b border-surface-700 bg-white px-6 flex items-center justify-between">
      <h1 className="text-base font-bold text-surface-100">
        {TITLES[pathname] || 'Nickel Knowledge Map'}
      </h1>
      <div className="flex items-center gap-3">
        <div className="relative" ref={panelRef}>
          <button
            type="button"
            className="btn-ghost relative p-2"
            onClick={() => setShowNotif(v => !v)}
            title="Уведомления"
          >
            <Bell size={16} />
            {unread > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-brand-600 text-white text-[9px] font-bold flex items-center justify-center">
                {unread > 9 ? '9+' : unread}
              </span>
            )}
          </button>
          {showNotif && (
            <div className="absolute right-0 top-full mt-2 w-80 card shadow-card-hover z-50 max-h-96 overflow-y-auto">
              <div className="flex items-center justify-between p-3 border-b border-surface-700">
                <span className="text-sm font-semibold">Уведомления</span>
                <button type="button" className="btn-ghost p-1" onClick={() => setShowNotif(false)}>
                  <X size={14} />
                </button>
              </div>
              {notifications.length === 0 ? (
                <p className="p-4 text-xs text-surface-400 text-center">Нет новых</p>
              ) : (
                notifications.map(n => (
                  <button
                    key={n.id}
                    type="button"
                    className={clsx(
                      'w-full text-left p-3 border-b border-surface-800 hover:bg-surface-900 transition-colors',
                      !n.read && 'bg-brand-50/50',
                    )}
                    onClick={() => markRead(n.id)}
                  >
                    <p className="text-sm font-medium text-surface-100">{n.title}</p>
                    <p className="text-xs text-surface-400 mt-0.5 line-clamp-2">{n.body}</p>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-surface-400">
          <span className={ok ? 'w-2 h-2 rounded-full bg-accent-400 animate-pulse' : 'w-2 h-2 rounded-full bg-red-400'} />
          {ok ? 'Система активна' : 'Деградация'}
          {health?.status && (
            <span className="badge bg-surface-900 text-surface-400">{health.status}</span>
          )}
        </div>
      </div>
    </header>
  )
}
