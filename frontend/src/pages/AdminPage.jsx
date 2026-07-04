import { useCallback, useEffect, useState } from 'react'
import { Shield, UserPlus, RefreshCw, KeyRound, Trash2, Loader2, Copy, Check, ScrollText, FileKey2 } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

function KeyReveal({ apiKey, onDismiss }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    await navigator.clipboard.writeText(apiKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="card p-4 border-brand-200 bg-brand-50 space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-brand-700">
        <KeyRound size={16} />
        API-ключ (показывается один раз)
      </div>
      <div className="flex items-center gap-2">
        <code className="flex-1 input font-mono text-xs break-all bg-white">{apiKey}</code>
        <button type="button" className="btn-secondary shrink-0" onClick={copy}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? 'Скопировано' : 'Копировать'}
        </button>
      </div>
      <p className="text-xs text-surface-400">Сохраните ключ — повторно он не будет показан.</p>
      {onDismiss && (
        <button type="button" className="btn-ghost text-xs" onClick={onDismiss}>Скрыть</button>
      )}
    </div>
  )
}

export default function AdminPage() {
  const { auth, user } = useAuth()
  const [tab, setTab] = useState('users')
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState([])
  const [audit, setAudit] = useState([])
  const [documents, setDocuments] = useState([])
  const [envAdminEmail, setEnvAdminEmail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [revealedKey, setRevealedKey] = useState('')
  const [creating, setCreating] = useState(false)

  const [newEmail, setNewEmail] = useState('')
  const [newName, setNewName] = useState('')
  const [newRole, setNewRole] = useState('')
  const [newKey, setNewKey] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [status, rolesData, usersData] = await Promise.all([
        api.authStatus(),
        api.listRoles(auth),
        api.listUsers(auth),
      ])
      setEnvAdminEmail(status.env_admin_email || null)
      setRoles(rolesData.roles || [])
      setUsers(usersData.users || [])
      setNewRole(prev => prev || rolesData.roles?.[0]?.role || '')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [auth])

  const loadAudit = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const rows = await api.listAuditLog(auth, { limit: 100 })
      setAudit(Array.isArray(rows) ? rows : [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [auth])

  const loadDocuments = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.listDocuments(auth, { limit: 200 })
      setDocuments(res.documents || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [auth])

  useEffect(() => {
    if (tab === 'users') load()
    else if (tab === 'audit') loadAudit()
    else if (tab === 'documents') loadDocuments()
  }, [tab, load, loadAudit, loadDocuments])

  const flash = (msg) => {
    setSuccess(msg)
    setTimeout(() => setSuccess(''), 4000)
  }

  const createUser = async (e) => {
    e.preventDefault()
    setCreating(true)
    setError('')
    setRevealedKey('')
    try {
      const body = { email: newEmail, name: newName, role: newRole }
      if (newKey.trim()) body.api_key = newKey.trim()
      const res = await api.createUser(auth, body)
      setRevealedKey(res.api_key)
      setNewEmail('')
      setNewName('')
      setNewKey('')
      flash('Пользователь создан')
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setCreating(false)
    }
  }

  const changeRole = async (userId, role) => {
    setError('')
    try {
      await api.updateUser(auth, userId, { role })
      flash('Роль обновлена')
      await load()
    } catch (e) {
      setError(e.message)
      await load()
    }
  }

  const rotateKey = async (userId) => {
    if (!confirm('Сгенерировать новый API-ключ? Старый перестанет работать.')) return
    setError('')
    setRevealedKey('')
    try {
      const res = await api.rotateUserKey(auth, userId)
      setRevealedKey(res.api_key)
      flash('Ключ обновлён')
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const deleteUser = async (userId, email) => {
    if (!confirm(`Удалить пользователя ${email}?`)) return
    setError('')
    try {
      await api.deleteUser(auth, userId)
      flash('Пользователь удалён')
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const changeDocAccess = async (sourceDocument, access_level) => {
    setError('')
    try {
      await api.setDocumentAccess(auth, sourceDocument, access_level)
      flash('Уровень доступа обновлён')
      await loadDocuments()
    } catch (e) {
      setError(e.message)
    }
  }

  const assignableRoles = roles.map(r => r.role)

  const ACTION_LABELS = {
    'auth.token': 'Вход в систему',
    'search.agent': 'Запрос к ассистенту',
    'document.upload': 'Загрузка документа',
    'admin.create_user': 'Создание пользователя',
    'admin.update_user': 'Изменение пользователя',
    'admin.delete_user': 'Удаление пользователя',
    'admin.rotate_key': 'Смена ключа',
    'admin.document_access': 'Изменение доступа к документу',
    'job.cancel': 'Отмена обработки',
    'fact.verify': 'Верификация факта',
  }

  const ACCESS_LABELS = {
    internal: 'Внутренний',
    partner: 'Партнёрский',
    public: 'Публичный',
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-brand-100 text-brand-700">
            <Shield size={20} />
          </div>
          <div>
            <h2 className="section-title text-base">Пользователи и доступ</h2>
            <p className="text-xs text-surface-400 mt-0.5">
              {user?.name} ({user?.email}) — {user?.role}
            </p>
          </div>
        </div>
        <button type="button" className="btn-ghost text-xs" onClick={() => {
          if (tab === 'users') load()
          else if (tab === 'audit') loadAudit()
          else loadDocuments()
        }} disabled={loading}>
          <RefreshCw size={13} className={clsx(loading && 'animate-spin-slow')} /> Обновить
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {[
          ['users', UserPlus, 'Пользователи'],
          ['audit', ScrollText, 'Журнал действий'],
          ['documents', FileKey2, 'Доступ к документам'],
        ].map(([id, Icon, label]) => (
          <button key={id} type="button" onClick={() => setTab(id)}
            className={clsx('flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border',
              tab === id ? 'bg-brand-600 text-white border-brand-600' : 'border-surface-700')}>
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      {error && (
        <div className="card p-4 border-red-200 bg-red-50 text-red-600 text-sm">{error}</div>
      )}
      {success && (
        <div className="card p-4 border-emerald-200 bg-emerald-50 text-emerald-700 text-sm">{success}</div>
      )}
      {revealedKey && (
        <KeyReveal apiKey={revealedKey} onDismiss={() => setRevealedKey('')} />
      )}

      {tab === 'users' && (
      <>
      <div className="card p-5 space-y-4">
        <h3 className="section-title text-sm flex items-center gap-2">
          <UserPlus size={16} /> Новый пользователь
        </h3>
        <form onSubmit={createUser} className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="label mb-1.5 block">Email</label>
            <input
              type="email"
              className="input"
              value={newEmail}
              onChange={e => setNewEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label mb-1.5 block">Имя</label>
            <input
              type="text"
              className="input"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label mb-1.5 block">Роль</label>
            <select className="input" value={newRole} onChange={e => setNewRole(e.target.value)} required>
              {assignableRoles.map(r => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label mb-1.5 block">API-ключ (опционально)</label>
            <input
              type="text"
              className="input font-mono text-sm"
              placeholder="Авто-генерация, если пусто"
              value={newKey}
              onChange={e => setNewKey(e.target.value)}
              minLength={16}
            />
          </div>
          <div className="md:col-span-2">
            <button type="submit" className="btn-primary" disabled={creating}>
              {creating ? <Loader2 size={14} className="animate-spin-slow" /> : <UserPlus size={14} />}
              Создать
            </button>
          </div>
        </form>
      </div>

      <div className="card overflow-hidden">
        <div className="px-5 py-4 border-b border-surface-700">
          <h3 className="section-title text-sm">Список пользователей</h3>
        </div>
        {loading ? (
          <div className="p-8 text-center text-surface-400 text-sm">
            <Loader2 size={20} className="mx-auto animate-spin-slow mb-2" />
            Загрузка…
          </div>
        ) : users.length === 0 ? (
          <div className="p-8 text-center text-surface-400 text-sm">Нет пользователей</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-700 bg-surface-900/50">
                  <th className="text-left px-4 py-3 label">Email</th>
                  <th className="text-left px-4 py-3 label">Имя</th>
                  <th className="text-left px-4 py-3 label">Роль</th>
                  <th className="text-left px-4 py-3 label">Ключ</th>
                  <th className="text-left px-4 py-3 label">Действия</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => {
                  const isEnvAdmin = envAdminEmail && u.email === envAdminEmail
                  return (
                    <tr key={u.id} className="border-b border-surface-700/50 hover:bg-surface-900/30">
                      <td className="px-4 py-3 font-mono text-xs">{u.email}</td>
                      <td className="px-4 py-3">{u.name}</td>
                      <td className="px-4 py-3">
                        {isEnvAdmin ? (
                          <span className="badge bg-brand-100 text-brand-700 border border-brand-200">
                            admin
                          </span>
                        ) : (
                          <select
                            className="input text-xs py-1 max-w-[180px]"
                            value={u.role}
                            onChange={e => changeRole(u.id, e.target.value)}
                          >
                            {assignableRoles.map(r => (
                              <option key={r} value={r}>{r}</option>
                            ))}
                          </select>
                        )}
                        {isEnvAdmin && (
                          <span className="text-[10px] text-surface-400 ml-1">(основной)</span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-surface-400">
                        {u.key_hint || '—'}
                      </td>
                      <td className="px-4 py-3">
                        {isEnvAdmin ? (
                          <span className="text-xs text-surface-400">ключ из конфигурации</span>
                        ) : (
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              className="btn-secondary text-xs py-1"
                              onClick={() => rotateKey(u.id)}
                            >
                              <KeyRound size={12} /> Новый ключ
                            </button>
                            <button
                              type="button"
                              className="btn-ghost text-xs text-red-500 hover:text-red-600 hover:bg-red-50"
                              onClick={() => deleteUser(u.id, u.email)}
                              disabled={u.id === user?.id}
                            >
                              <Trash2 size={12} /> Удалить
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {roles.length > 0 && (
        <div className="card p-5 space-y-3">
          <h3 className="section-title text-sm">Роли</h3>
          <div className="space-y-2">
            {roles.map(r => (
              <div key={r.role} className="flex flex-wrap items-start gap-2 text-sm">
                <span className="badge bg-surface-900 text-surface-300 border border-surface-700 shrink-0">
                  {r.role}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      </>
      )}

      {tab === 'audit' && (
        <div className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-surface-700">
            <h3 className="section-title text-sm">Журнал действий</h3>
          </div>
          {loading ? (
            <div className="p-8 text-center text-surface-400 text-sm">
              <Loader2 size={20} className="mx-auto animate-spin-slow mb-2" />
              Загрузка…
            </div>
          ) : audit.length === 0 ? (
            <div className="p-8 text-center text-surface-400 text-sm">Записей пока нет</div>
          ) : (
            <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-surface-900">
                  <tr className="border-b border-surface-700">
                    <th className="text-left px-4 py-3 label">Когда</th>
                    <th className="text-left px-4 py-3 label">Действие</th>
                    <th className="text-left px-4 py-3 label">Роль</th>
                    <th className="text-left px-4 py-3 label">Объект</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map(row => (
                    <tr key={row.id} className="border-b border-surface-700/50">
                      <td className="px-4 py-2 text-xs text-surface-400 whitespace-nowrap">{row.created_at}</td>
                      <td className="px-4 py-2">{ACTION_LABELS[row.action] || row.action}</td>
                      <td className="px-4 py-2 text-xs">{row.user_role || '—'}</td>
                      <td className="px-4 py-2 text-xs text-surface-400 truncate max-w-[200px]">{row.resource || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'documents' && (
        <div className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-surface-700">
            <h3 className="section-title text-sm">Уровень доступа к документам</h3>
          </div>
          {loading ? (
            <div className="p-8 text-center text-surface-400 text-sm">
              <Loader2 size={20} className="mx-auto animate-spin-slow mb-2" />
              Загрузка…
            </div>
          ) : documents.length === 0 ? (
            <div className="p-8 text-center text-surface-400 text-sm">Документы не найдены</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-700 bg-surface-900/50">
                    <th className="text-left px-4 py-3 label">Документ</th>
                    <th className="text-left px-4 py-3 label">Тип</th>
                    <th className="text-left px-4 py-3 label">Доступ</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map(doc => (
                    <tr key={doc.source_document || doc.id} className="border-b border-surface-700/50">
                      <td className="px-4 py-3 font-mono text-xs">{doc.source_document || doc.filename}</td>
                      <td className="px-4 py-3 text-xs">{doc.document_kind || '—'}</td>
                      <td className="px-4 py-3">
                        <select
                          className="input text-xs py-1 max-w-[160px]"
                          value={doc.access_level || 'internal'}
                          onChange={e => changeDocAccess(doc.source_document || doc.filename, e.target.value)}
                        >
                          {Object.entries(ACCESS_LABELS).map(([val, label]) => (
                            <option key={val} value={val}>{label}</option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
