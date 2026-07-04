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

function isAbortError(err) {
  return err?.name === 'AbortError' || /abort/i.test(String(err?.message || ''))
}

export function AuthProvider({ children }) {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(STORAGE_KEY) || '')
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

  const clearSession = useCallback((message = '') => {
    localStorage.removeItem(STORAGE_KEY)
    clearCachedToken()
    setApiKey('')
    setToken('')
    setUser(null)
    setError(message)
  }, [])

  const refreshSession = useCallback(async (key) => {
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    const seq = ++sessionSeq.current
    const { signal } = ac

    if (!key) {
      setUser(null)
      setToken('')
      setLoading(false)
      setError('')
      return
    }

    setLoading(true)
    setError('')

    try {
      const cached = loadCachedToken()
      if (cached) {
        try {
          const me = await api.me({ token: cached }, signal)
          if (seq !== sessionSeq.current || signal.aborted) return
          setToken(cached)
          setUser(me)
          setError('')
          return
        } catch {
          clearCachedToken()
        }
      }

      const tok = await api.authToken(key, signal)
      if (seq !== sessionSeq.current || signal.aborted) return
      saveCachedToken(tok)
      setToken(tok.access_token)

      const me = await api.me({ token: tok.access_token }, signal)
      if (seq !== sessionSeq.current || signal.aborted) return
      setUser(me)
      setError('')
    } catch (e) {
      if (isAbortError(e) || signal.aborted || seq !== sessionSeq.current) return
      clearSession(e.message)
    } finally {
      if (seq === sessionSeq.current) setLoading(false)
    }
  }, [clearSession])

  useEffect(() => {
    refreshSession(apiKey)
    return () => {
      sessionSeq.current += 1
      abortRef.current?.abort()
    }
  }, [apiKey, refreshSession])

  const login = (key) => {
    const trimmed = key.trim()
    clearCachedToken()
    localStorage.setItem(STORAGE_KEY, trimmed)
    setApiKey(trimmed)
  }

  const logout = () => {
    sessionSeq.current += 1
    abortRef.current?.abort()
    clearSession('')
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
