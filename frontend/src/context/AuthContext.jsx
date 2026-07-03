import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { api } from '../api/client'

const AuthContext = createContext(null)
const STORAGE_KEY = 'nickel_api_key'

export function AuthProvider({ children }) {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(STORAGE_KEY) || '')
  const [token, setToken] = useState('')
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const auth = token ? { token } : apiKey ? { apiKey } : {}

  const refreshSession = useCallback(async (key) => {
    if (!key) {
      setUser(null)
      setToken('')
      setLoading(false)
      return
    }
    try {
      const tok = await api.authToken(key)
      setToken(tok.access_token)
      const me = await api.me({ token: tok.access_token })
      setUser(me)
      setError('')
    } catch (e) {
      setError(e.message)
      setUser(null)
      setToken('')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshSession(apiKey)
  }, [apiKey, refreshSession])

  const login = (key) => {
    localStorage.setItem(STORAGE_KEY, key.trim())
    setApiKey(key.trim())
    setLoading(true)
  }

  const logout = () => {
    localStorage.removeItem(STORAGE_KEY)
    setApiKey('')
    setToken('')
    setUser(null)
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
