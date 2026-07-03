import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import LoginPage from './pages/LoginPage'
import IngestPage from './pages/IngestPage'
import SearchPage from './pages/SearchPage'
import { useAuth } from './context/AuthContext'

function RequireAuth({ children }) {
  const { apiKey, loading } = useAuth()
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-950">
        <div className="text-surface-400 text-sm">Загрузка…</div>
      </div>
    )
  }
  if (!apiKey) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/jobs" replace />} />
          <Route path="jobs" element={<IngestPage />} />
          <Route path="search" element={<SearchPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
