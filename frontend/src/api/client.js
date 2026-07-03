const API_BASE = import.meta.env.VITE_API_URL || ''

function headers(apiKey, token) {
  const h = { Accept: 'application/json' }
  if (token) h.Authorization = `Bearer ${token}`
  else if (apiKey) h['X-API-Key'] = apiKey
  return h
}

async function request(path, { apiKey, token, method = 'GET', body, formData } = {}) {
  const opts = { method, headers: headers(apiKey, token) }
  if (formData) {
    opts.body = formData
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(`${API_BASE}${path}`, opts)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const err = await res.json()
      detail = err.detail || JSON.stringify(err)
    } catch { /* ignore */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (res.status === 204) return null
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json()
  return res.text()
}

export const api = {
  authStatus: () => request('/api/v1/auth/status'),
  authToken: (api_key) => request('/api/v1/auth/token', { method: 'POST', body: { api_key } }),
  me: (auth) => request('/api/v1/auth/me', auth),

  listJobs: (auth, { active, limit = 100, batch_id } = {}) => {
    const q = new URLSearchParams({ limit })
    if (active) q.set('active', 'true')
    if (batch_id) q.set('batch_id', batch_id)
    return request(`/api/v1/jobs?${q}`, auth)
  },
  getJob: (auth, id) => request(`/api/v1/jobs/${id}`, auth),
  getJobLogs: (auth, id, sinceId = 0) =>
    request(`/api/v1/jobs/${id}/logs?since_id=${sinceId}`, auth),
  getJobChildren: (auth, id) => request(`/api/v1/jobs/${id}/children`, auth),

  listFolders: (auth) => request('/api/v1/ingest/folders', auth),
  ingestFolder: (auth, folder_path, extractor, recursive) =>
    request('/api/v1/documents/ingest-folder', {
      ...auth,
      method: 'POST',
      body: { folder_path, extractor: extractor || null, recursive },
    }),
  uploadFile: (auth, file, extractor) => {
    const fd = new FormData()
    fd.append('file', file)
    const q = extractor ? `?extractor=${extractor}` : ''
    return request(`/api/v1/documents/upload${q}`, { ...auth, method: 'POST', formData: fd })
  },

  hybridSearch: (auth, query, limit = 10) =>
    request('/api/v1/search/hybrid', {
      ...auth,
      method: 'POST',
      body: { query, limit },
    }),

  health: () => request('/health'),
}
