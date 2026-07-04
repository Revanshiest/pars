import { useCallback, useEffect, useState } from 'react'
import { FileText, Loader2, RefreshCw, Lock, Trash2 } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

const LEVELS = [
  { value: 'internal', label: 'Внутренний', color: 'bg-red-50 text-red-700 border-red-200' },
  { value: 'partner', label: 'Партнёр', color: 'bg-amber-50 text-amber-700 border-amber-200' },
  { value: 'public', label: 'Публичный', color: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
]

function shortJob(id) {
  if (!id) return '—'
  return id.length > 10 ? `${id.slice(0, 8)}…` : id
}

export default function DocumentsPage() {
  const { auth } = useAuth()
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.listDocuments(auth)
      setDocs(Array.isArray(data) ? data : data.documents || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [auth])

  useEffect(() => { load() }, [load])

  const setAccess = async (sourceDocument, access_level) => {
    setBusy(`acl:${sourceDocument}`)
    try {
      await api.updateDocumentAccess(auth, sourceDocument, access_level)
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  const removeDoc = async (doc) => {
    const label = doc.source_document || doc.id
    const msg = `Удалить импорт «${label}»?\n\nБудут удалены: запись документа, связанные факты (SQLite), рёбра в Neo4j и векторы в Qdrant для job ${shortJob(doc.job_id)}.`
    if (!window.confirm(msg)) return
    setBusy(`del:${doc.id}`)
    setError('')
    try {
      const res = await api.deleteDocument(auth, doc.id)
      await load()
      if (res.facts_removed > 0) {
        setError('')
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-surface-100 flex items-center gap-2">
            <FileText size={20} className="text-brand-600" />
            Документы и доступ
          </h2>
          <p className="text-xs text-surface-400 mt-1">
            ACL: internal / partner / public. Дубликаты — повторные импорты (разные job_id).
          </p>
        </div>
        <button type="button" className="btn-ghost text-xs" onClick={load} disabled={loading}>
          <RefreshCw size={13} /> Обновить
        </button>
      </div>

      {error && <div className="card p-4 text-red-600 text-sm">{error}</div>}

      {loading ? (
        <div className="flex justify-center py-16 text-surface-400">
          <Loader2 size={20} className="animate-spin-slow mr-2" /> Загрузка…
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-surface-400 border-b border-surface-700 bg-surface-900/50">
                <th className="p-3 font-medium">Документ</th>
                <th className="p-3 font-medium">Тип</th>
                <th className="p-3 font-medium">Год</th>
                <th className="p-3 font-medium">Job</th>
                <th className="p-3 font-medium">Доступ</th>
                <th className="p-3 font-medium w-12" />
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-800">
              {docs.map(d => {
                const level = LEVELS.find(l => l.value === (d.access_level || 'internal'))
                const isBusy = busy === `del:${d.id}` || busy === `acl:${d.source_document}`
                return (
                  <tr key={d.id}>
                    <td className="p-3">
                      <p className="font-medium text-surface-100">{d.source_document}</p>
                      {d.author && d.author.length < 80 && (
                        <p className="text-xs text-surface-400 mt-0.5">{d.author}</p>
                      )}
                      {d.created_at && (
                        <p className="text-[10px] text-surface-500 mt-0.5">
                          {new Date(d.created_at).toLocaleString('ru-RU')}
                        </p>
                      )}
                    </td>
                    <td className="p-3 text-xs text-surface-400">{d.document_kind || '—'}</td>
                    <td className="p-3 text-xs tabular-nums">{d.year || '—'}</td>
                    <td className="p-3 text-[10px] font-mono text-surface-500" title={d.job_id}>
                      {shortJob(d.job_id)}
                    </td>
                    <td className="p-3">
                      <select
                        className="input text-xs max-w-[130px]"
                        value={d.access_level || 'internal'}
                        disabled={isBusy}
                        onChange={e => setAccess(d.source_document, e.target.value)}
                      >
                        {LEVELS.map(l => (
                          <option key={l.value} value={l.value}>{l.label}</option>
                        ))}
                      </select>
                      {level && (
                        <span className={clsx('badge border ml-1 text-[10px] hidden sm:inline-flex', level.color)}>
                          <Lock size={9} className="inline mr-0.5" />{level.label}
                        </span>
                      )}
                    </td>
                    <td className="p-3">
                      <button
                        type="button"
                        className="btn-ghost p-1.5 text-red-500 hover:bg-red-50"
                        title="Удалить импорт и связанные факты"
                        disabled={isBusy}
                        onClick={() => removeDoc(d)}
                      >
                        {busy === `del:${d.id}` ? (
                          <Loader2 size={14} className="animate-spin-slow" />
                        ) : (
                          <Trash2 size={14} />
                        )}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {docs.length === 0 && (
            <p className="text-center py-10 text-surface-400 text-sm">Документов пока нет</p>
          )}
        </div>
      )}
    </div>
  )
}
