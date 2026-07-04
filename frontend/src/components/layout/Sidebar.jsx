import { NavLink } from 'react-router-dom'
import {
  Upload, Search, Network, BookOpen, Shield, ChevronLeft, ChevronRight,
  Atom, LogOut, BarChart3, ShieldCheck, FileText,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../../context/AuthContext'

const ROLE_PERMS = {
  researcher: ['synthesis'],
  analyst: ['verify', 'export', 'compare', 'edit_graph'],
  project_manager: ['dashboard', 'verify', 'export', 'compare', 'audit', 'edit_graph'],
  admin: ['*'],
}

function can(role, perm) {
  const p = ROLE_PERMS[role] || []
  return p.includes('*') || p.includes(perm)
}

const NAV = [
  { to: '/jobs', icon: Upload, label: 'Обработка', desc: 'Папки и задачи' },
  { to: '/search', icon: Search, label: 'Исследование', desc: 'Поиск и аналитика' },
  { to: '/graph', icon: Network, label: 'Граф', desc: 'Визуализация знаний' },
  { to: '/glossary', icon: BookOpen, label: 'Глоссарий', desc: 'Термины и синонимы' },
]

const EXTRA_NAV = [
  { to: '/dashboard', icon: BarChart3, label: 'Дашборд', desc: 'Метрики R&D', perm: 'dashboard' },
  { to: '/verify', icon: ShieldCheck, label: 'Верификация', desc: 'Проверка фактов', perm: 'verify' },
  { to: '/documents', icon: FileText, label: 'Документы', desc: 'Уровни доступа', perm: 'audit' },
]

export default function Sidebar({ collapsed, onToggle }) {
  const { user, logout } = useAuth()
  const initials = (user?.name || user?.email || '?')
    .split(/[\s@]/)
    .slice(0, 2)
    .map(s => s[0]?.toUpperCase())
    .join('')

  const items = [
    ...NAV,
    ...EXTRA_NAV.filter(n => can(user?.role, n.perm)),
    ...(user?.role === 'admin' ? [
      { to: '/admin', icon: Shield, label: 'Пользователи', desc: 'Управление доступом' },
    ] : []),
  ]

  return (
    <aside className={clsx(
      'flex flex-col bg-white border-r border-surface-700 transition-all duration-300 shrink-0 shadow-card',
      collapsed ? 'w-16' : 'w-60',
    )}>
      <div className={clsx(
        'flex items-center gap-3 px-4 py-5 border-b border-surface-700',
        collapsed && 'justify-center px-0',
      )}>
        <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: 'linear-gradient(135deg, #5302e0 60%, #00ffbf 100%)' }}>
          <Atom size={17} className="text-white" />
        </div>
        {!collapsed && (
          <div>
            <div className="text-sm font-black text-surface-100 leading-none">Nickel</div>
            <div className="text-[10px] text-surface-400 mt-0.5">R&D Knowledge Map</div>
          </div>
        )}
      </div>

      <nav className="flex-1 py-3 space-y-0.5 px-2 overflow-y-auto">
        {items.map(({ to, icon: Icon, label, desc }) => (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? label : undefined}
            className={({ isActive }) => clsx(
              'nav-item',
              isActive ? 'nav-item-active' : 'nav-item-idle',
              collapsed && 'justify-center px-0',
            )}
          >
            <Icon size={17} className="shrink-0" />
            {!collapsed && (
              <div>
                <div className="text-sm font-semibold leading-none">{label}</div>
                <div className="text-[11px] opacity-60 mt-0.5">{desc}</div>
              </div>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="p-2 border-t border-surface-700 space-y-0.5">
        {!collapsed && user && (
          <div className="mx-2 mb-2 px-3 py-2 bg-surface-900 rounded-xl border border-surface-700">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-black text-white bg-brand-600">
                {initials}
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-surface-100 truncate">{user.name}</div>
                <div className="text-[10px] text-surface-400">{user.role}</div>
              </div>
            </div>
          </div>
        )}
        <button onClick={logout} className={clsx('btn-ghost w-full', collapsed && 'justify-center')} title="Выйти">
          <LogOut size={15} />
          {!collapsed && <span className="text-xs">Выйти</span>}
        </button>
        <button onClick={onToggle} className="btn-ghost w-full justify-center">
          {collapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
        </button>
      </div>
    </aside>
  )
}
