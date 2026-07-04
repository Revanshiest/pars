import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header from './Header'
import GlobalJobsPanel from '../jobs/GlobalJobsPanel'
import { useState } from 'react'

export default function Layout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden bg-surface-950">
      <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(v => !v)} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-6 animate-fade-in">
          <Outlet />
        </main>
      </div>
      <GlobalJobsPanel />
    </div>
  )
}
