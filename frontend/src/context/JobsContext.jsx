import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { useAuth } from './AuthContext'
import { api } from '../api/client'

const JobsContext = createContext(null)

export function JobsProvider({ children }) {
  const { token, apiKey } = useAuth()
  const [jobs, setJobs] = useState([])
  const [expanded, setExpanded] = useState({})
  const [error, setError] = useState('')

  const refreshJobs = useCallback(async () => {
    if (!token && !apiKey) return
    const auth = token ? { token } : { apiKey }
    try {
      const list = await api.listJobs(auth, { limit: 100 })
      setJobs(list)
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [token, apiKey])

  useEffect(() => {
    refreshJobs()
    const t = setInterval(refreshJobs, 10000)
    return () => clearInterval(t)
  }, [refreshJobs])

  const expandJob = useCallback((jobId) => {
    setExpanded(prev => ({ ...prev, [jobId]: true }))
  }, [])

  const toggleExpanded = useCallback((jobId) => {
    setExpanded(prev => ({ ...prev, [jobId]: !prev[jobId] }))
  }, [])

  const activeJobs = jobs.filter(j => j.status === 'running' || j.status === 'pending')

  return (
    <JobsContext.Provider value={{
      jobs,
      activeJobs,
      expanded,
      error,
      refreshJobs,
      expandJob,
      toggleExpanded,
    }}>
      {children}
    </JobsContext.Provider>
  )
}

export function useJobs() {
  const ctx = useContext(JobsContext)
  if (!ctx) throw new Error('useJobs must be used within JobsProvider')
  return ctx
}
