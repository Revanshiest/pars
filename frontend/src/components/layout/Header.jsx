import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../../api/client'

const TITLES = {
  '/jobs': 'Обработка документов',
  '/search': 'Поиск знаний',
}

export default function Header() {
  const { pathname } = useLocation()
  const [health, setHealth] = useState(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: 'unavailable' }))
    const t = setInterval(() => {
      api.health().then(setHealth).catch(() => setHealth({ status: 'unavailable' }))
    }, 30000)
    return () => clearInterval(t)
  }, [])

  const ok = health?.status === 'ok' || health?.status === 'degraded'

  return (
    <header className="h-14 shrink-0 border-b border-surface-700 bg-white px-6 flex items-center justify-between">
      <h1 className="text-base font-bold text-surface-100">
        {TITLES[pathname] || 'Nickel Knowledge Map'}
      </h1>
      <div className="flex items-center gap-2 text-xs text-surface-400">
        <span className={ok ? 'w-2 h-2 rounded-full bg-accent-400 animate-pulse' : 'w-2 h-2 rounded-full bg-red-400'} />
        {ok ? 'Система активна' : 'Деградация / недоступна'}
        {health?.status && (
          <span className="badge bg-surface-900 text-surface-400 ml-1">{health.status}</span>
        )}
      </div>
    </header>
  )
}
