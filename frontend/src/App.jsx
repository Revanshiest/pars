import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import LoginPage from './pages/LoginPage'
import IngestPage from './pages/IngestPage'
import SearchPage from './pages/SearchPage'
import GraphPage from './pages/GraphPage'
import GlossaryPage from './pages/GlossaryPage'
import AdminPage from './pages/AdminPage'
import { useAuth } from './context/AuthContext'
import { JobsProvider } from './context/JobsContext'

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
          <Route
            path="admin"
            element={
              <RequireAdmin>
                <AdminPage />
              </RequireAdmin>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
