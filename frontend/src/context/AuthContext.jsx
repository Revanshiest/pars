import { createContext, useContext, useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { api } from '../api/client'

const AuthContext = createContext(null)
const STORAGE_KEY = 'nickel_api_key'
const TOKEN_KEY = 'nickel_access_token'
const TOKEN_EXP_KEY = 'nickel_token_exp'

function loadCachedToken() {
  try {
    const t = sessionStorage.getItem(TOKEN_KEY)
    const exp = sessionStorage.getItem(TOKEN_EXP_KEY)
    if (!t || !exp) return null
    if (Date.now() / 1000 > Number(exp) - 60) {
      sessionStorage.removeItem(TOKEN_KEY)
      sessionStorage.removeItem(TOKEN_EXP_KEY)
      return null
    }
    return t
  } catch {
    return null
  }
}

function saveCachedToken(tok) {
  try {
    sessionStorage.setItem(TOKEN_KEY, tok.access_token)
    const expSec = tok.expires_at
      ? Math.floor(new Date(tok.expires_at).getTime() / 1000)
      : Math.floor(Date.now() / 1000) + (tok.expires_in || 86400)
    sessionStorage.setItem(TOKEN_EXP_KEY, String(expSec))
  } catch { /* ignore */ }
}

function clearCachedToken() {
  try {
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(TOKEN_EXP_KEY)
  } catch { /* ignore */ }
}

function normalizeKey(key) {
  let k = (key || '').trim().replace(/^["']|["']$/g, '')
  // AUTH_ADMIN=email|name|api_key — часто вставляют всю строку целиком
  const parts = k.split('|').map(p => p.trim())
  if (parts.length >= 3 && parts[0].includes('@')) {
    k = parts[parts.length - 1]
  }
  return k.replace(/^["']|["']$/g, '')
}

function isAbortError(err) {
  return err?.name === 'AbortError' || /abort/i.test(String(err?.message || ''))
}

function formatError(err) {
  const msg = err?.message || 'Ошибка авторизации'
  if (typeof msg === 'string' && msg.startsWith('[')) {
    try {
      const parsed = JSON.parse(msg)
      if (Array.isArray(parsed) && parsed[0]?.msg) return parsed[0].msg
    } catch { /* ignore */ }
  }
  return msg
}

export function AuthProvider({ children }) {
  const [apiKey, setApiKey] = useState(() => normalizeKey(localStorage.getItem(STORAGE_KEY) || ''))
  const [token, setToken] = useState('')
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const sessionSeq = useRef(0)
  const abortRef = useRef(null)

  const auth = useMemo(() => {
    if (token) return { token }
    if (apiKey) return { apiKey }
    return {}
  }, [token, apiKey])

  const wipeCredentials = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    clearCachedToken()
    setApiKey('')
    setToken('')
    setUser(null)
  }, [])

  const establishSession = useCallback(async (key, { showError = false } = {}) => {
    const trimmed = normalizeKey(key)
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    const seq = ++sessionSeq.current
    const { signal } = ac

    if (!trimmed) {
      setUser(null)
      setToken('')
      setLoading(false)
      if (showError) setError('')
      return false
    }

    setLoading(true)
    if (showError) setError('')

    try {
      const cached = loadCachedToken()
      if (cached) {
        try {
          const me = await api.me({ token: cached }, signal)
          if (seq !== sessionSeq.current || signal.aborted) return false
          setToken(cached)
          setUser(me)
          setApiKey(trimmed)
          localStorage.setItem(STORAGE_KEY, trimmed)
          setError('')
          return true
        } catch {
          clearCachedToken()
        }
      }

      const tok = await api.authToken(trimmed, signal)
      if (seq !== sessionSeq.current || signal.aborted) return false
      saveCachedToken(tok)
      setToken(tok.access_token)

      const me = await api.me({ token: tok.access_token }, signal)
      if (seq !== sessionSeq.current || signal.aborted) return false
      setUser(me)
      setApiKey(trimmed)
      localStorage.setItem(STORAGE_KEY, trimmed)
      setError('')
      return true
    } catch (e) {
      if (isAbortError(e) || signal.aborted || seq !== sessionSeq.current) return false
      wipeCredentials()
      if (showError) {
        setError(formatError(e))
      }
      return false
    } finally {
      if (seq === sessionSeq.current) setLoading(false)
    }
  }, [wipeCredentials])

  useEffect(() => {
    const isLoginPage = /^\/login\/?$/.test(window.location.pathname)
    if (isLoginPage) {
      wipeCredentials()
      setLoading(false)
      return
    }
    const stored = normalizeKey(localStorage.getItem(STORAGE_KEY) || '')
    void establishSession(stored, { showError: false })
    return () => {
      sessionSeq.current += 1
      abortRef.current?.abort()
    }
  }, [establishSession, wipeCredentials])

  const login = useCallback(async (key) => {
    const trimmed = normalizeKey(key)
    if (!trimmed) return false
    setError('')
    clearCachedToken()
    localStorage.setItem(STORAGE_KEY, trimmed)
    setApiKey(trimmed)
    return establishSession(trimmed, { showError: true })
  }, [establishSession])

  const logout = () => {
    sessionSeq.current += 1
    abortRef.current?.abort()
    wipeCredentials()
    setError('')
  }

  return (
    <AuthContext.Provider value={{ apiKey, token, user, auth, loading, error, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
