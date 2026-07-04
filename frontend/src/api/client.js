const API_BASE = import.meta.env.VITE_API_URL || ''

function headers(apiKey, token) {
  const h = { Accept: 'application/json' }
  if (token) h.Authorization = `Bearer ${token}`
  else if (apiKey) h['X-API-Key'] = apiKey
  return h
}

async function request(path, { apiKey, token, method = 'GET', body, formData, signal, responseType } = {}) {
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
  if (responseType === 'text') return res.text()
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
  cancelJob: (auth, id) => request(`/api/v1/jobs/${id}/cancel`, { ...auth, method: 'POST' }),
  getJobLogs: (auth, id, sinceId = 0) =>
    request(`/api/v1/jobs/${id}/logs?since_id=${sinceId}`, auth),
  getJobChildren: (auth, id) => request(`/api/v1/jobs/${id}/children`, auth),

  listFolders: (auth) => request('/api/v1/ingest/folders', auth),
  ingestFolder: (auth, folder_path, extractor, recursive, mode = 'full') =>
    request('/api/v1/documents/ingest-folder', {
      ...auth,
      method: 'POST',
      body: { folder_path, extractor: extractor || null, recursive, mode },
    }),
  uploadFile: (auth, file, extractor) => {
    const fd = new FormData()
    fd.append('file', file)
    const q = extractor ? `?extractor=${encodeURIComponent(extractor)}` : ''
    return request(`/api/v1/documents/upload${q}`, { ...auth, method: 'POST', formData: fd })
  },

  getGraphView: (auth, { limit = 0, full = false, entity_name, source_document } = {}) => {
    const q = new URLSearchParams()
    if (limit > 0) q.set('limit', limit)
    if (full) q.set('full', 'true')
    if (entity_name) q.set('entity_name', entity_name)
    if (source_document) q.set('source_document', source_document)
    return request(`/api/v1/graph/view?${q}`, auth)
  },

  getGraphHtml: (auth, { limit = 500, entity_name, source_document } = {}) => {
    const q = new URLSearchParams({ limit })
    if (entity_name) q.set('entity_name', entity_name)
    if (source_document) q.set('source_document', source_document)
    return request(`/api/v1/graph/html?${q}`, { ...auth, responseType: 'text' })
  },

  addTriple: (auth, body) =>
    request('/api/v1/graph/triples', { ...auth, method: 'POST', body }),
  updateTriple: (auth, factId, body) =>
    request(`/api/v1/graph/triples/${encodeURIComponent(factId)}`, { ...auth, method: 'PATCH', body }),
  deleteTriple: (auth, factId, comment = '') => {
    const q = comment ? `?comment=${encodeURIComponent(comment)}` : ''
    return request(`/api/v1/graph/triples/${encodeURIComponent(factId)}${q}`, { ...auth, method: 'DELETE' })
  },
  listGraphEdits: (auth, limit = 50) =>
    request(`/api/v1/graph/edits?limit=${limit}`, auth),
  getFactVersions: (auth, factId) =>
    request(`/api/v1/facts/${encodeURIComponent(factId)}/versions`, auth),
  syncGraph: (auth) =>
    request('/api/v1/graph/sync', { ...auth, method: 'POST' }),

  filteredSearch: (auth, body) =>
    request('/api/v1/search/filtered', { ...auth, method: 'POST', body }),

  hybridSearch: (auth, query, limit = 20) =>
    request('/api/v1/search/hybrid', {
      ...auth,
      method: 'POST',
      body: { query, limit },
    }),

  numericSearch: (auth, query, { limit = 50, geography, verification_status } = {}) =>
    request('/api/v1/search/numeric', {
      ...auth,
      method: 'POST',
      body: { query, limit, geography, verification_status },
    }),

  comparePractices: (auth, query, extra = {}) =>
    request('/api/v1/search/compare-practices', {
      ...auth,
      method: 'POST',
      body: { query, limit: 15, ...extra },
    }),

  agentSearch: (auth, question, { max_iterations = 5, signal } = {}) =>
    request('/api/v1/search/agent', {
      ...auth,
      method: 'POST',
      body: { question, max_iterations },
      signal,
    }),

  dashboard: (auth) => request('/api/v1/dashboard', auth),

  knowledgeGaps: (auth, params = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
    })
    return request(`/api/v1/analytics/gaps?${q}`, auth)
  },

  searchExamples: (auth) => request('/api/v1/search/examples', auth),

  ontologyGaps: (auth, body) =>
    request('/api/v1/analytics/gaps/ontology', { ...auth, method: 'POST', body }),

  literatureReview: (auth, topic, { geography, min_confidence, use_llm } = {}) =>
    request('/api/v1/synthesis/literature-review', {
      ...auth,
      method: 'POST',
      body: { topic, geography, min_confidence, use_llm },
    }),

  compareTechnologies: (auth, technologies, parameters) =>
    request('/api/v1/analytics/compare', {
      ...auth,
      method: 'POST',
      body: { technologies, parameters },
    }),

  recommendations: (auth, topic) =>
    request(`/api/v1/analytics/recommendations?topic=${encodeURIComponent(topic)}`, auth),

  exportReport: (auth, topic, format) =>
    request('/api/v1/export', { ...auth, method: 'POST', body: { topic, format } }),

  downloadExportUrl: (topic, format) =>
    `${API_BASE}/api/v1/export/${encodeURIComponent(topic)}/download?format=${encodeURIComponent(format)}`,

  verificationQueue: (auth, { limit = 50, unassigned_only } = {}) => {
    const q = new URLSearchParams({ limit })
    if (unassigned_only) q.set('unassigned_only', 'true')
    return request(`/api/v1/verification/queue?${q}`, auth)
  },

  myVerificationQueue: (auth, limit = 20) =>
    request(`/api/v1/verification/my-queue?limit=${limit}`, auth),

  verifyFact: (auth, factId, status, notes = '') =>
    request(`/api/v1/facts/${factId}/verify`, {
      ...auth,
      method: 'POST',
      body: { status, notes },
    }),

  claimVerificationTasks: (auth, limit = 5) =>
    request('/api/v1/verification/claim', { ...auth, method: 'POST', body: { limit } }),

  getOntology: (auth) => request('/api/v1/ontology', auth),

  health: () => request('/health'),

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

  listGlossary: (auth, { domain, q, limit = 200, offset = 0 } = {}) => {
    const params = new URLSearchParams({ limit, offset })
    if (domain) params.set('domain', domain)
    if (q) params.set('q', q)
    return request(`/api/v1/glossary?${params}`, auth)
  },
  listGlossaryDomains: (auth) => request('/api/v1/glossary/domains', auth),
  createGlossaryTerm: (auth, body) =>
    request('/api/v1/glossary', { ...auth, method: 'POST', body }),
  glossaryLookup: (auth, text, top_k = 5) =>
    request('/api/v1/glossary/lookup', { ...auth, method: 'POST', body: { text, top_k } }),

  listNotifications: (auth, unreadOnly = false) =>
    request(`/api/v1/notifications?unread_only=${unreadOnly}`, auth),
  markNotificationRead: (auth, id) =>
    request(`/api/v1/notifications/${id}/read`, { ...auth, method: 'POST' }),

  listSubscriptions: (auth) => request('/api/v1/subscriptions', auth),
  subscribe: (auth, topic, filters = {}) =>
    request('/api/v1/subscriptions', { ...auth, method: 'POST', body: { topic, filters } }),
  unsubscribe: (auth, subscriptionId) =>
    request(`/api/v1/subscriptions/${subscriptionId}`, { ...auth, method: 'DELETE' }),

  listAuditLog: (auth, { limit = 100 } = {}) =>
    request(`/api/v1/audit?limit=${limit}`, auth),
  listDocuments: (auth, { access_level, limit = 100 } = {}) => {
    const q = new URLSearchParams({ limit })
    if (access_level) q.set('access_level', access_level)
    return request(`/api/v1/documents?${q}`, auth)
  },
  setDocumentAccess: (auth, sourceDocument, access_level) =>
    request(`/api/v1/documents/${encodeURIComponent(sourceDocument)}/access`, {
      ...auth,
      method: 'PATCH',
      body: { access_level },
    }),
}
