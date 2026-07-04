import { useCallback, useEffect, useState } from 'react'
import { BookOpen, Loader2, Plus, RefreshCw, Search, Sparkles, Pencil, Trash2 } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

const CAN_WRITE = new Set(['analyst', 'admin'])

function SynonymList({ items, lang }) {
  if (!items?.length) return <span className="text-surface-400">—</span>
  return (
    <div className="flex flex-wrap gap-1">
      {items.map(s => (
        <span key={s} className="badge bg-surface-900 text-surface-300 border border-surface-700 text-[10px]">
          {lang && <span className="opacity-50 mr-0.5">{lang}</span>}{s}
        </span>
      ))}
    </div>
  )
}

export default function GlossaryPage() {
  const { auth, user } = useAuth()
  const [terms, setTerms] = useState([])
  const [allDomains, setAllDomains] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [domain, setDomain] = useState('')
  const [lookupText, setLookupText] = useState('')
  const [lookupLoading, setLookupLoading] = useState(false)
  const [lookupResults, setLookupResults] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState(null)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({
    canonical: '',
    domain: '',
    definition: '',
    synonyms_ru: '',
    synonyms_en: '',
  })

  const canWrite = CAN_WRITE.has(user?.role)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = {}
      if (domain) params.domain = domain
      if (search.trim()) params.q = search.trim()
      const list = await api.listGlossary(auth, params)
      setTerms(Array.isArray(list) ? list : [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [auth, domain, search])

  useEffect(() => {
    api.listGlossary(auth).then(list => {
      const doms = [...new Set((Array.isArray(list) ? list : []).map(t => t.domain).filter(Boolean))].sort()
      setAllDomains(doms)
    }).catch(() => {})
  }, [auth])

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0)
    return () => clearTimeout(t)
  }, [load, search])

  const runLookup = async (e) => {
    e.preventDefault()
    if (lookupText.trim().length < 2) return
    setLookupLoading(true)
    setLookupResults(null)
    try {
      const res = await api.glossaryLookup(auth, lookupText.trim())
      setLookupResults(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setLookupLoading(false)
    }
  }

  const createTerm = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const body = {
        canonical: form.canonical.trim(),
        domain: form.domain.trim() || null,
        definition: form.definition.trim() || null,
        synonyms_ru: form.synonyms_ru.split(',').map(s => s.trim()).filter(Boolean),
        synonyms_en: form.synonyms_en.split(',').map(s => s.trim()).filter(Boolean),
      }
      if (editId) {
        await api.updateGlossaryTerm(auth, editId, body)
        setEditId(null)
      } else {
        await api.createGlossaryTerm(auth, body)
      }
      setForm({ canonical: '', domain: '', definition: '', synonyms_ru: '', synonyms_en: '' })
      setShowForm(false)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const startEdit = (t) => {
    setEditId(t.id)
    setForm({
      canonical: t.canonical,
      domain: t.domain || '',
      definition: t.definition || '',
      synonyms_ru: (t.synonyms_ru || []).join(', '),
      synonyms_en: (t.synonyms_en || []).join(', '),
    })
    setShowForm(true)
  }

  const removeTerm = async (id) => {
    if (!window.confirm('Удалить термин?')) return
    setBusy(true)
    try {
      await api.deleteGlossaryTerm(auth, id)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-surface-100 flex items-center gap-2">
            <BookOpen size={20} className="text-brand-600" />
            Глоссарий
          </h2>
          <p className="text-xs text-surface-400 mt-1">
            Термины RU/EN для нормализации сущностей и расширения поиска (BGE-m3)
          </p>
        </div>
        <div className="flex gap-2">
          {canWrite && (
            <button type="button" className="btn-secondary text-xs" onClick={() => setShowForm(v => !v)}>
              <Plus size={13} /> Добавить
            </button>
          )}
          <button type="button" className="btn-ghost text-xs" onClick={load} disabled={loading}>
            <RefreshCw size={13} /> Обновить
          </button>
        </div>
      </div>

      {error && (
        <div className="card p-4 border-red-200 bg-red-50 text-red-600 text-sm">{error}</div>
      )}

      <div className="card p-5">
        <h3 className="section-title text-sm flex items-center gap-2 mb-3">
          <Sparkles size={15} className="text-violet-500" />
          Семантический поиск (BGE)
        </h3>
        <form onSubmit={runLookup} className="flex gap-2">
          <input
            className="input text-sm flex-1"
            placeholder="Фрагмент текста или термин…"
            value={lookupText}
            onChange={e => setLookupText(e.target.value)}
            minLength={2}
          />
          <button type="submit" className="btn-primary shrink-0" disabled={lookupLoading || lookupText.length < 2}>
            {lookupLoading ? <Loader2 size={14} className="animate-spin-slow" /> : <Search size={14} />}
            Найти
          </button>
        </form>
        {lookupResults && (
          <div className="mt-4 space-y-2">
            <p className="text-xs text-surface-400">
              Совпадения для «{lookupResults.text}»:
            </p>
            {lookupResults.matches?.length === 0 && (
              <p className="text-sm text-surface-400">Ничего не найдено (порог similarity 0.72)</p>
            )}
            {lookupResults.matches?.map(m => (
              <div key={m.canonical + m.matched_form} className="flex items-center gap-3 p-3 rounded-xl bg-surface-900 border border-surface-700">
                <span className="text-sm font-semibold text-surface-100">{m.canonical}</span>
                <span className="text-xs text-surface-400">← {m.matched_form}</span>
                <span className="badge bg-violet-100 text-violet-700 border border-violet-200 ml-auto">
                  {m.score}
                </span>
                <span className="text-[10px] text-surface-400 uppercase">{m.lang}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {showForm && canWrite && (
        <div className="card p-5">
          <h3 className="section-title text-sm mb-4">{editId ? 'Редактировать' : 'Новый'} термин</h3>
          <form onSubmit={createTerm} className="grid md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className="label mb-1.5 block">Каноническое имя</label>
              <input className="input text-sm" required value={form.canonical}
                onChange={e => setForm(f => ({ ...f, canonical: e.target.value }))} />
            </div>
            <div>
              <label className="label mb-1.5 block">Домен / тип</label>
              <input className="input text-sm" placeholder="Material, Process…" value={form.domain}
                onChange={e => setForm(f => ({ ...f, domain: e.target.value }))} />
            </div>
            <div>
              <label className="label mb-1.5 block">Синонимы RU (через запятую)</label>
              <input className="input text-sm" value={form.synonyms_ru}
                onChange={e => setForm(f => ({ ...f, synonyms_ru: e.target.value }))} />
            </div>
            <div>
              <label className="label mb-1.5 block">Синонимы EN (через запятую)</label>
              <input className="input text-sm" value={form.synonyms_en}
                onChange={e => setForm(f => ({ ...f, synonyms_en: e.target.value }))} />
            </div>
            <div className="md:col-span-2">
              <label className="label mb-1.5 block">Определение</label>
              <textarea className="input text-sm min-h-[72px]" value={form.definition}
                onChange={e => setForm(f => ({ ...f, definition: e.target.value }))} />
            </div>
            <div className="md:col-span-2">
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? <Loader2 size={14} className="animate-spin-slow" /> : <Plus size={14} />}
                Сохранить
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card p-5">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <h3 className="section-title text-sm flex-1">
            Термины {loading ? '…' : `(${terms.length})`}
          </h3>
          <input
            className="input text-sm max-w-xs"
            placeholder="Поиск…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <select className="input text-sm max-w-[160px]" value={domain} onChange={e => setDomain(e.target.value)}>
            <option value="">Все домены</option>
            {allDomains.map(d => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12 text-surface-400">
            <Loader2 size={20} className="animate-spin-slow mr-2" /> Загрузка…
          </div>
        ) : terms.length === 0 ? (
          <p className="text-sm text-surface-400 text-center py-8">Термины не найдены</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-surface-400 border-b border-surface-700">
                  <th className="pb-2 pr-3 font-medium">Термин</th>
                  <th className="pb-2 pr-3 font-medium">Домен</th>
                  <th className="pb-2 pr-3 font-medium">RU</th>
                  <th className="pb-2 pr-3 font-medium">EN</th>
                  <th className="pb-2 font-medium">Источник</th>
                  {canWrite && <th className="pb-2 font-medium w-20" />}
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-800">
                {terms.map(t => (
                  <tr key={t.id} className="align-top">
                    <td className="py-3 pr-3">
                      <div className="font-semibold text-surface-100">{t.canonical}</div>
                      {t.definition && (
                        <p className="text-xs text-surface-400 mt-1 max-w-xs">{t.definition}</p>
                      )}
                    </td>
                    <td className="py-3 pr-3">
                      {t.domain ? (
                        <span className={clsx('badge border bg-brand-100 text-brand-700 border-brand-200')}>{t.domain}</span>
                      ) : '—'}
                    </td>
                    <td className="py-3 pr-3 max-w-[180px]">
                      <SynonymList items={t.synonyms_ru} />
                    </td>
                    <td className="py-3 pr-3 max-w-[180px]">
                      <SynonymList items={t.synonyms_en} />
                    </td>
                    <td className="py-3 text-xs text-surface-400">{t.source || '—'}</td>
                    {canWrite && (
                      <td className="py-3">
                        <div className="flex gap-1">
                          <button type="button" className="btn-ghost p-1" onClick={() => startEdit(t)} title="Изменить">
                            <Pencil size={13} />
                          </button>
                          <button type="button" className="btn-ghost p-1 text-red-500" onClick={() => removeTerm(t.id)} title="Удалить">
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
