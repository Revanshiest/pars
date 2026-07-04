import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import LoginPage from './pages/LoginPage'
import IngestPage from './pages/IngestPage'
import SearchPage from './pages/SearchPage'
import GraphPage from './pages/GraphPage'
import GlossaryPage from './pages/GlossaryPage'
import AdminPage from './pages/AdminPage'
import DashboardPage from './pages/DashboardPage'
import VerificationPage from './pages/VerificationPage'
import DocumentsPage from './pages/DocumentsPage'
import { useAuth } from './context/AuthContext'
import { JobsProvider } from './context/JobsContext'

const ROLE_PERMS = {
  researcher: ['read', 'search', 'upload', 'subscribe', 'glossary_read', 'synthesis'],
  analyst: ['read', 'search', 'upload', 'verify', 'edit_graph', 'export', 'subscribe', 'glossary_read', 'glossary_write', 'synthesis', 'compare'],
  project_manager: ['read', 'search', 'upload', 'verify', 'edit_graph', 'export', 'dashboard', 'compare', 'subscribe', 'glossary_read', 'synthesis', 'audit'],
  admin: ['*'],
  external_partner: ['read', 'search', 'glossary_read'],
}

function hasPerm(role, perm) {
  const perms = ROLE_PERMS[role] || []
  return perms.includes('*') || perms.includes(perm)
}

function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-950">
        <div className="text-surface-400 text-sm">Загрузка…</div>
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return children
}

function GuestOnly({ children }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-950">
        <div className="text-surface-400 text-sm">Загрузка…</div>
      </div>
    )
  }
  if (user) return <Navigate to="/jobs" replace />
  return children
}

function RequireAdmin({ children }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-950">
        <div className="text-surface-400 text-sm">Загрузка…</div>
      </div>
    )
  }
  if (user?.role !== 'admin') return <Navigate to="/jobs" replace />
  return children
}

function RequirePerm({ perm, children }) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!hasPerm(user?.role, perm)) return <Navigate to="/jobs" replace />
  return children
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <JobsProvider>
                <Layout />
              </JobsProvider>
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/jobs" replace />} />
          <Route path="jobs" element={<IngestPage />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="graph" element={<GraphPage />} />
          <Route path="glossary" element={<GlossaryPage />} />
          <Route path="dashboard" element={<RequirePerm perm="dashboard"><DashboardPage /></RequirePerm>} />
          <Route path="verify" element={<RequirePerm perm="verify"><VerificationPage /></RequirePerm>} />
          <Route path="documents" element={<RequirePerm perm="audit"><DocumentsPage /></RequirePerm>} />
          <Route path="admin" element={<RequireAdmin><AdminPage /></RequireAdmin>} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
