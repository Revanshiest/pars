import { useState, useEffect } from 'react'
import { KeyRound } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'

export default function LoginPage() {
  const { login, error, loading, apiKey, user } = useAuth()
  const [key, setKey] = useState('')
  const [pending, setPending] = useState(false)
  const [setupRequired, setSetupRequired] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    fetch('/api/v1/auth/status')
      .then(r => r.json())
      .then(s => setSetupRequired(!!s.setup_required))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (pending && !loading && error) setPending(false)
  }, [pending, loading, error])

  useEffect(() => {
    if (!pending) return
    if (!loading && apiKey && user) {
      navigate('/search')
      setPending(false)
    }
  }, [pending, loading, apiKey, user, navigate])

  const submit = async (e) => {
    e.preventDefault()
    login(key)
    setPending(true)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-950 p-4">
      <div className="card p-8 w-full max-w-md space-y-6">
        <div className="text-center">
          <div className="w-14 h-14 mx-auto rounded-2xl flex items-center justify-center mb-4"
            style={{ background: 'linear-gradient(135deg, #5302e0 60%, #00ffbf 100%)' }}>
            <KeyRound size={24} className="text-white" />
          </div>
          <h1 className="text-xl font-bold text-surface-100">НОРНИК R&D Knowledge Map</h1>
          <p className="text-sm text-surface-400 mt-2">
            Единая карта знаний горно-металлургических исследований: публикации, эксперименты,
            технологии, материалы, эксперты.
          </p>
        </div>

        {setupRequired && (
          <p className="text-sm text-surface-400 text-center">
            Пример: <code className="text-xs">AUTH_ADMIN=admin@org|Admin|your-api-key-min-16</code>
          </p>
        )}

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="label mb-1.5 block">API Key</label>
            <input
              type="password"
              className="input font-mono"
              placeholder="nickel_..."
              value={key}
              onChange={e => setKey(e.target.value)}
              minLength={16}
              required
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <button type="submit" className="btn-primary w-full justify-center" disabled={loading}>
            {loading ? 'Проверка…' : 'Войти'}
          </button>
        </form>
      </div>
    </div>
  )
}
