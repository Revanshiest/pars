import { useState } from 'react'
import { KeyRound, ExternalLink } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'

export default function LoginPage() {
  const { login, error, loading } = useAuth()
  const [key, setKey] = useState('')
  const navigate = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    login(key)
    navigate('/jobs')
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-950 p-4">
      <div className="card p-8 w-full max-w-md space-y-6">
        <div className="text-center">
          <div className="w-14 h-14 mx-auto rounded-2xl flex items-center justify-center mb-4"
            style={{ background: 'linear-gradient(135deg, #5302e0 60%, #00ffbf 100%)' }}>
            <KeyRound size={24} className="text-white" />
          </div>
          <h1 className="text-xl font-bold text-surface-100">Nickel Knowledge Map</h1>
          <p className="text-sm text-surface-400 mt-2">
            Введите API-ключ. Получить его можно в{' '}
            <a href="/admin/" className="text-brand-600 hover:underline inline-flex items-center gap-0.5">
              админ-панели <ExternalLink size={12} />
            </a>
          </p>
        </div>

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
