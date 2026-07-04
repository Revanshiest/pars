import { useState } from 'react'
import { KeyRound, Loader2, AlertCircle } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export default function LoginPage() {
  const { login, error, loading, user } = useAuth()
  const [key, setKey] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const busy = loading || submitting

  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    setSubmitting(true)
    try {
      await login(key)
    } finally {
      setSubmitting(false)
    }
  }

  if (user) return null

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-950 p-4">
      <div className="card p-8 w-full max-w-md space-y-6 shadow-xl border-surface-700/80">
        <div className="text-center space-y-3">
          <div
            className="w-14 h-14 mx-auto rounded-2xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #5302e0 60%, #00ffbf 100%)' }}
          >
            <KeyRound size={24} className="text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-surface-100 tracking-tight">Nickel Knowledge Map</h1>
            <p className="text-sm text-surface-400 mt-1.5">
              Вход по API-ключу организации
            </p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor="api-key" className="label mb-1.5 block">
              API-ключ
            </label>
            <input
              id="api-key"
              type="password"
              className="input font-mono w-full"
              value={key}
              onChange={e => setKey(e.target.value)}
              onBlur={e => setKey(e.target.value.trim())}
              disabled={busy}
              autoFocus
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              name="nickel-api-key"
            />
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-600">
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <button type="submit" className="btn-primary w-full justify-center" disabled={busy}>
            {busy ? (
              <>
                <Loader2 size={16} className="animate-spin-slow" />
                Проверка…
              </>
            ) : (
              'Войти'
            )}
          </button>
        </form>

        <p className="text-xs text-center text-surface-500 leading-relaxed">
          Первый администратор задаётся в <code className="text-surface-400">AUTH_ADMIN</code>.
          Остальные ключи выдаёт admin в разделе «Пользователи».
        </p>
      </div>
    </div>
  )
}
