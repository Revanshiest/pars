const API_BASE = import.meta.env.VITE_API_URL || ''

function headers(apiKey, token) {
  const h = { Accept: 'application/json' }
  if (token) h.Authorization = `Bearer ${token}`
  else if (apiKey) h['X-API-Key'] = apiKey
  return h
}

async function request(path, { apiKey, token, method = 'GET', body, formData, signal } = {}) {
  const opts = { method, headers: headers(apiKey, token), signal }
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
  authToken: (api_key, signal) =>
    request('/api/v1/auth/token', { method: 'POST', body: { api_key }, signal }),
  me: (auth, signal) => request('/api/v1/auth/me', { ...auth, signal }),

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
  ingestFolder: (auth, folder_path, extractor, recursive, mode = 'full') =>
    request('/api/v1/documents/ingest-folder', {
      ...auth, method: 'POST',
      body: { folder_path, extractor: extractor || null, recursive, mode },
    }),
  uploadFile: (auth, file, extractor) => {
    const fd = new FormData()
    fd.append('file', file)
    const q = extractor ? `?extractor=${extractor}` : ''
    return request(`/api/v1/documents/upload${q}`, { ...auth, method: 'POST', formData: fd })
  },
  importPair: (auth, document, jsonFile) => {
    const fd = new FormData()
    fd.append('document', document)
    fd.append('json_file', jsonFile)
    return request('/api/v1/documents/import-pair', { ...auth, method: 'POST', formData: fd })
  },
  importPairs: (auth, files) => {
    const fd = new FormData()
    for (const file of files) fd.append('files', file)
    return request('/api/v1/documents/import-pairs', { ...auth, method: 'POST', formData: fd })
  },
  uploadFolder: (auth, files, mode = 'full', extractor) => {
    const fd = new FormData()
    for (const file of files) fd.append('files', file)
    fd.append('mode', mode)
    if (extractor && extractor !== 'auto') fd.append('extractor', extractor)
    return request('/api/v1/documents/upload-folder', { ...auth, method: 'POST', formData: fd })
  },

  getGraphView: (auth, { limit = 200, entity_name } = {}) => {
    const q = new URLSearchParams({ limit })
    if (entity_name) q.set('entity_name', entity_name)
    return request(`/api/v1/graph/view?${q}`, auth)
  },
  getGraphStats: (auth) => request('/api/v1/graph/stats', auth),
  addTriple: (auth, body) =>
    request('/api/v1/graph/triples', { ...auth, method: 'POST', body }),
  syncGraph: (auth) =>
    request('/api/v1/graph/sync', { ...auth, method: 'POST' }),
  updateTriple: (auth, factId, body) =>
    request(`/api/v1/graph/triples/${factId}`, { ...auth, method: 'PATCH', body }),
  deleteTriple: (auth, factId, comment = '') =>
    request(`/api/v1/graph/triples/${factId}?comment=${encodeURIComponent(comment)}`, {
      ...auth, method: 'DELETE',
    }),
  listGraphEdits: (auth) => request('/api/v1/graph/edits', auth),

  hybridSearch: (auth, body) =>
    request('/api/v1/search/hybrid', { ...auth, method: 'POST', body }),
  filteredSearch: (auth, body) =>
    request('/api/v1/search/filtered', { ...auth, method: 'POST', body }),
  numericSearch: (auth, body) =>
    request('/api/v1/search/numeric', { ...auth, method: 'POST', body }),
  comparePractices: (auth, body) =>
    request('/api/v1/search/compare-practices', { ...auth, method: 'POST', body }),
  agentSearch: (auth, question) =>
    request('/api/v1/search/agent', { ...auth, method: 'POST', body: { question } }),

  listFacts: (auth, params = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => { if (v != null && v !== '') q.set(k, v) })
    const qs = q.toString()
    return request(`/api/v1/facts${qs ? `?${qs}` : ''}`, auth)
  },
  getFact: (auth, id) => request(`/api/v1/facts/${id}`, auth),
  verifyFact: (auth, id, body) =>
    request(`/api/v1/facts/${id}/verify`, { ...auth, method: 'POST', body }),
  getFactVersions: (auth, id) => request(`/api/v1/facts/${id}/versions`, auth),

  verificationQueue: (auth, params = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => { if (v != null && v !== '') q.set(k, v) })
    const qs = q.toString()
    return request(`/api/v1/verification/queue${qs ? `?${qs}` : ''}`, auth)
  },
  myVerificationQueue: (auth) => request('/api/v1/verification/my-queue', auth),
  claimVerification: (auth, limit = 5) =>
    request('/api/v1/verification/claim', { ...auth, method: 'POST', body: { limit } }),

  literatureReview: (auth, body) =>
    request('/api/v1/synthesis/literature-review', { ...auth, method: 'POST', body }),
  analyticsGaps: (auth, params = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => { if (v != null && v !== '') q.set(k, v) })
    const qs = q.toString()
    return request(`/api/v1/analytics/gaps${qs ? `?${qs}` : ''}`, auth)
  },
  ontologyGaps: (auth, body) =>
    request('/api/v1/analytics/gaps/ontology', { ...auth, method: 'POST', body }),
  recommendations: (auth, topic) =>
    request(`/api/v1/analytics/recommendations?topic=${encodeURIComponent(topic)}`, auth),
  compareTechnologies: (auth, body) =>
    request('/api/v1/analytics/compare', { ...auth, method: 'POST', body }),
  sourcesBreakdown: (auth) => request('/api/v1/analytics/sources-breakdown', auth),

  dashboard: (auth) => request('/api/v1/dashboard', auth),

  exportReport: (auth, body) =>
    request('/api/v1/export', { ...auth, method: 'POST', body }),
  exportDownloadUrl: (topic) =>
    `${API_BASE}/api/v1/export/${encodeURIComponent(topic)}/download`,

  listDocuments: (auth) => request('/api/v1/documents', auth),
  updateDocumentAccess: (auth, sourceDocument, access_level) =>
    request(`/api/v1/documents/${encodeURIComponent(sourceDocument)}/access`, {
      ...auth, method: 'PATCH', body: { access_level },
    }),
  deleteDocument: (auth, docId) =>
    request(`/api/v1/documents/${encodeURIComponent(docId)}`, { ...auth, method: 'DELETE' }),

  listNotifications: (auth, unread_only = false) =>
    request(`/api/v1/notifications${unread_only ? '?unread_only=true' : ''}`, auth),
  markNotificationRead: (auth, id) =>
    request(`/api/v1/notifications/${id}/read`, { ...auth, method: 'POST' }),
  listSubscriptions: (auth) => request('/api/v1/subscriptions', auth),
  createSubscription: (auth, body) =>
    request('/api/v1/subscriptions', { ...auth, method: 'POST', body }),

  listAudit: (auth, limit = 100) =>
    request(`/api/v1/audit?limit=${limit}`, auth),

  health: () => request('/health'),
  getOntology: (auth) => request('/api/v1/ontology', auth),

  listRoles: (auth) => request('/api/v1/admin/roles', auth),
  listUsers: (auth) => request('/api/v1/admin/users', auth),
  createUser: (auth, body) =>
    request('/api/v1/admin/users', { ...auth, method: 'POST', body }),
  updateUser: (auth, userId, body) =>
    request(`/api/v1/admin/users/${userId}`, { ...auth, method: 'PATCH', body }),
  deleteUser: (auth, userId) =>
    request(`/api/v1/admin/users/${userId}`, { ...auth, method: 'DELETE' }),
  rotateUserKey: (auth, userId) =>
    request(`/api/v1/admin/users/${userId}/rotate-key`, { ...auth, method: 'POST' }),

  listGlossary: (auth, { domain, q } = {}) => {
    const params = new URLSearchParams()
    if (domain) params.set('domain', domain)
    if (q) params.set('q', q)
    const qs = params.toString()
    return request(`/api/v1/glossary${qs ? `?${qs}` : ''}`, auth)
  },
  createGlossaryTerm: (auth, body) =>
    request('/api/v1/glossary', { ...auth, method: 'POST', body }),
  updateGlossaryTerm: (auth, id, body) =>
    request(`/api/v1/glossary/${id}`, { ...auth, method: 'PATCH', body }),
  deleteGlossaryTerm: (auth, id) =>
    request(`/api/v1/glossary/${id}`, { ...auth, method: 'DELETE' }),
  glossaryLookup: (auth, text, top_k = 5) =>
    request('/api/v1/glossary/lookup', { ...auth, method: 'POST', body: { text, top_k } }),
}
