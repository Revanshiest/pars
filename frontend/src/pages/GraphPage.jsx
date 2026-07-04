import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Search, ZoomIn, ZoomOut, Maximize2, X, RotateCcw,
  Loader2, Network, Plus, GitBranch, Filter, Pencil, Trash2, History,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'
import VisGraphCanvas from '../graph/VisGraphCanvas'
import { EdgeFactCard } from '../graph/EdgeFactCard'
import {
  RELATION_META_FALLBACK,
  relationLabel,
  relationDescription,
  relationColor,
  edgeKey,
  edgeRelation,
  edgeFactText,
  TYPE_CFG,
  nodeTypeStyle,
} from '../graph/constants'

export default function GraphPage() {
  const { auth, user } = useAuth()
  const canEdit = ['analyst', 'project_manager', 'admin'].includes(user?.role)
  const [searchParams, setSearchParams] = useSearchParams()
  const centerEntity = searchParams.get('entity') || searchParams.get('entity_name') || ''
  const sourceDoc = searchParams.get('source') || ''

  const canvasRef = useRef(null)
  const [graphData, setGraphData] = useState({ nodes: [], edges: [], documents: [] })
  const [relationMeta, setRelationMeta] = useState(RELATION_META_FALLBACK)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [selectedEdge, setSelectedEdge] = useState(null)
  const [hovered, setHovered] = useState(null)
  const [hoveredEdge, setHoveredEdge] = useState(null)
  const [search, setSearch] = useState(centerEntity)
  const [nodeFilter, setNodeFilter] = useState('')
  const [relationFilter, setRelationFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [showAllLabels, setShowAllLabels] = useState(false)
  const [loadFull, setLoadFull] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [addBusy, setAddBusy] = useState(false)
  const [triple, setTriple] = useState({
    subject: '', subject_type: 'Material', relation: 'related_to',
    object: '', object_type: 'Process', comment: '',
  })
  const [edgeEdit, setEdgeEdit] = useState(null)
  const [edgeEditComment, setEdgeEditComment] = useState('')
  const [factVersions, setFactVersions] = useState([])
  const [graphEdits, setGraphEdits] = useState([])
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    api.getOntology(auth).then(data => {
      if (data?.relation_meta) setRelationMeta({ ...RELATION_META_FALLBACK, ...data.relation_meta })
    }).catch(() => {})
  }, [auth])

  useEffect(() => {
    setSearch(centerEntity)
  }, [centerEntity])

  const applyCenter = useCallback((name) => {
    const p = {}
    if (name) p.entity = name
    if (sourceDoc) p.source = sourceDoc
    setSearchParams(p)
  }, [sourceDoc, setSearchParams])

  useEffect(() => {
    const q = search.trim()
    if (q === centerEntity) return undefined
    if (!q) {
      if (centerEntity) applyCenter('')
      return undefined
    }
    const t = setTimeout(() => applyCenter(q), 500)
    return () => clearTimeout(t)
  }, [search, centerEntity, applyCenter])

  const apiNodes = graphData.nodes || []
  const apiEdges = graphData.edges || []
  const entityMode = Boolean(centerEntity.trim())
  const pendingSearch = Boolean(search.trim() && search.trim() !== centerEntity)
  const documents = graphData.documents || []

  const relationTypesInGraph = useMemo(() => {
    const s = new Set(apiEdges.map(e => edgeRelation(e)).filter(Boolean))
    return [...s].sort()
  }, [apiEdges])

  const nodeTypesInGraph = useMemo(() => {
    const s = new Set(apiNodes.map(n => n.type || 'Concept'))
    return [...s].sort((a, b) => {
      const order = Object.keys(TYPE_CFG)
      return (order.indexOf(a) === -1 ? 99 : order.indexOf(a)) - (order.indexOf(b) === -1 ? 99 : order.indexOf(b))
    })
  }, [apiNodes])

  useEffect(() => {
    setLoadFull(false)
  }, [centerEntity, sourceDoc])

  const shouldFetchFull = Boolean(centerEntity || sourceDoc || loadFull)

  const filteredNodes = useMemo(() =>
    apiNodes.filter(n => {
      if (typeFilter && (n.type || 'Concept') !== typeFilter) return false
      if (!nodeFilter) return true
      return (n.name || '').toLowerCase().includes(nodeFilter.toLowerCase())
    })
  , [apiNodes, nodeFilter, typeFilter])

  const filteredIds = useMemo(() => new Set(filteredNodes.map(n => n.id)), [filteredNodes])

  const filteredEdges = useMemo(() =>
    apiEdges.filter(e => {
      if (!filteredIds.has(e.source) || !filteredIds.has(e.target)) return false
      if (relationFilter && edgeRelation(e) !== relationFilter) return false
      return true
    })
  , [apiEdges, filteredIds, relationFilter])

  const connectedEdges = useMemo(() => {
    if (!selected) return []
    return filteredEdges.filter(e => e.source === selected || e.target === selected)
  }, [selected, filteredEdges])

  useEffect(() => {
    if (filteredNodes.length > 0 && !loading) setRendering(true)
    else setRendering(false)
  }, [filteredNodes.length, loading, centerEntity, sourceDoc, loadFull])

  const reloadGraph = useCallback(() => {
    setLoading(true)
    setRendering(false)
    setError('')
    return api.getGraphView(auth, {
      entity_name: centerEntity || undefined,
      source_document: sourceDoc || undefined,
      full: shouldFetchFull,
    })
      .then(data => setGraphData(data))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [auth, centerEntity, sourceDoc, shouldFetchFull])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setRendering(false)
    setError('')
    api.getGraphView(auth, {
      entity_name: centerEntity || undefined,
      source_document: sourceDoc || undefined,
      full: shouldFetchFull,
    })
      .then(data => { if (!cancelled) setGraphData(data) })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [auth, centerEntity, sourceDoc, shouldFetchFull])

  const syncFromSqlite = async () => {
    setAddBusy(true)
    setError('')
    try {
      await api.syncGraph(auth)
      await reloadGraph()
    } catch (err) {
      setError(err.message)
    } finally {
      setAddBusy(false)
    }
  }

  const submitTriple = async (e) => {
    e.preventDefault()
    setAddBusy(true)
    setError('')
    try {
      await api.addTriple(auth, triple)
      setShowAdd(false)
      setTriple({ subject: '', subject_type: 'Material', relation: 'related_to', object: '', object_type: 'Process', comment: '' })
      await reloadGraph()
      if (showHistory) loadEditHistory()
    } catch (err) {
      setError(err.message)
    } finally {
      setAddBusy(false)
    }
  }

  const loadEditHistory = useCallback(async () => {
    if (!canEdit) return
    try {
      const rows = await api.listGraphEdits(auth, 30)
      setGraphEdits(Array.isArray(rows) ? rows : [])
    } catch {
      setGraphEdits([])
    }
  }, [auth, canEdit])

  useEffect(() => {
    if (showHistory && canEdit) loadEditHistory()
  }, [showHistory, canEdit, loadEditHistory])

  useEffect(() => {
    const fid = selectedEdge?.fact_id
    if (!fid) {
      setFactVersions([])
      setEdgeEdit(null)
      return
    }
    setEdgeEdit({
      subject: selectedEdge.source_name || '',
      object: selectedEdge.target_name || '',
      relation: edgeRelation(selectedEdge),
      description: selectedEdge.description || '',
    })
    api.getFactVersions(auth, fid)
      .then(data => setFactVersions(data?.versions || []))
      .catch(() => setFactVersions([]))
  }, [selectedEdge, auth])

  const saveEdgeEdit = async () => {
    const fid = selectedEdge?.fact_id
    if (!fid || !edgeEdit) return
    setAddBusy(true)
    setError('')
    try {
      await api.updateTriple(auth, fid, {
        subject: edgeEdit.subject,
        object: edgeEdit.object,
        relation: edgeEdit.relation,
        properties: edgeEdit.description ? { description: edgeEdit.description } : undefined,
        comment: edgeEditComment,
      })
      setEdgeEditComment('')
      setSelectedEdge(null)
      await reloadGraph()
      if (showHistory) loadEditHistory()
    } catch (err) {
      setError(err.message)
    } finally {
      setAddBusy(false)
    }
  }

  const removeEdge = async () => {
    const fid = selectedEdge?.fact_id
    if (!fid || !window.confirm('Отметить связь как отклонённую (удалить из графа)?')) return
    setAddBusy(true)
    setError('')
    try {
      await api.deleteTriple(auth, fid, edgeEditComment || 'удалено экспертом')
      setEdgeEditComment('')
      setSelectedEdge(null)
      await reloadGraph()
      if (showHistory) loadEditHistory()
    } catch (err) {
      setError(err.message)
    } finally {
      setAddBusy(false)
    }
  }

  const selectNode = (id) => {
    setSelected(id)
    setSelectedEdge(null)
    if (id) canvasRef.current?.focusNode(id)
  }

  const selectEdge = (edge) => {
    setSelectedEdge(edge)
    setSelected(null)
  }

  const applySource = (doc) => {
    const p = {}
    if (centerEntity) p.entity = centerEntity
    if (doc) p.source = doc
    setSearchParams(p)
  }

  const selNode = apiNodes.find(n => n.id === selected)
  const nodeById = useMemo(() => Object.fromEntries(apiNodes.map(n => [n.id, n])), [apiNodes])
  const selectedEdgeId = selectedEdge ? (selectedEdge.visId || edgeKey(selectedEdge)) : null
  const panelOpen = selected || selectedEdge

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96 text-surface-400 gap-2">
        <Loader2 size={20} className="animate-spin-slow" />
        Загрузка графа…
      </div>
    )
  }

  return (
    <div className="h-full flex gap-4" style={{ height: 'calc(100vh - 8rem)' }}>
      <div className="w-64 shrink-0 flex flex-col gap-3 overflow-y-auto">
        <div className="card p-3">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-2.5 text-surface-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); applyCenter(search.trim()) } }}
              placeholder="Узел: медь, Cerro Verde…"
              className="input pl-8 py-2 text-xs"
            />
          </div>
          {!entityMode && search.trim() && pendingSearch && (
            <p className="text-[10px] text-surface-400 mt-2">Загрузка связей…</p>
          )}
          {centerEntity && (
            <div className="mt-2 flex items-center gap-1 text-[10px] text-brand-600 bg-brand-50 rounded-lg px-2 py-1">
              <Network size={10} />
              <span className="truncate flex-1">Центр: {centerEntity}</span>
              <button type="button" onClick={() => applyCenter('')}><X size={10} /></button>
            </div>
          )}
        </div>

        <div className="card p-3 space-y-2">
          <div className="label text-[10px]">Источник</div>
          <select
            className="input text-xs py-1.5"
            value={sourceDoc}
            onChange={e => applySource(e.target.value)}
          >
            <option value="">Все документы</option>
            {documents.map(d => (
              <option key={d.source_document} value={d.source_document}>
                {d.source_document} — {d.entities ?? '?'} узл., {d.facts} факт.
              </option>
            ))}
          </select>
          <div className="relative">
            <Search size={11} className="absolute left-2.5 top-2 text-surface-400" />
            <input
              value={nodeFilter}
              onChange={e => setNodeFilter(e.target.value)}
              placeholder="Фильтр узлов…"
              className="input pl-7 py-1.5 text-xs"
            />
          </div>
        </div>

        <div className="card p-3 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div className="text-center bg-brand-50 rounded-xl py-2">
              <div className="text-xl font-black text-brand-600">{filteredNodes.length}</div>
              <div className="text-[10px] text-brand-400">узлов</div>
            </div>
            <div className="text-center bg-surface-900 rounded-xl py-2">
              <div className="text-xl font-black text-surface-200">{filteredEdges.length}</div>
              <div className="text-[10px] text-surface-400">связей</div>
            </div>
          </div>
          <label className="flex items-center gap-2 text-[10px] text-surface-400 cursor-pointer">
            <input type="checkbox" checked={showAllLabels} onChange={e => setShowAllLabels(e.target.checked)} className="rounded" />
            Подписи всех связей
          </label>
          <p className="text-[10px] text-surface-500 leading-snug">
            {entityMode
              ? `Центр «${centerEntity}» — все связи.`
              : sourceDoc
                ? `Документ «${sourceDoc}».`
                : loadFull
                  ? 'Полный граф — живая физика, подписи у хабов.'
                  : 'Выберите документ или узел — быстрая загрузка.'}
          </p>
          {!shouldFetchFull && (
            <button type="button" className="btn-secondary w-full text-xs" onClick={() => setLoadFull(true)}>
              Загрузить весь граф
            </button>
          )}
          <div>
            <label className="label mb-1 flex items-center gap-1"><Filter size={10} /> Тип связи</label>
            <select className="input text-xs py-1.5" value={relationFilter} onChange={e => setRelationFilter(e.target.value)}>
              <option value="">Все ({apiEdges.length})</option>
              {relationTypesInGraph.map(r => (
                <option key={r} value={r}>
                  {relationMeta[r]?.label_ru || r.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
            {relationTypesInGraph.includes('contradicts') && (
              <button
                type="button"
                className={clsx(
                  'btn-secondary w-full text-xs mt-1',
                  relationFilter === 'contradicts' && 'border-red-300 text-red-600',
                )}
                onClick={() => setRelationFilter(relationFilter === 'contradicts' ? '' : 'contradicts')}
              >
                Противоречия
              </button>
            )}
          </div>
          <button type="button" onClick={() => canvasRef.current?.stabilize()} className="btn-secondary w-full text-xs">
            <RotateCcw size={11} /> Перезапустить физику
          </button>
        </div>

        {nodeTypesInGraph.length > 0 && (
          <div className="card p-3">
            <div className="label mb-2">Типы узлов</div>
            <div className="space-y-1 max-h-36 overflow-y-auto">
              <button
                type="button"
                onClick={() => setTypeFilter('')}
                className={clsx(
                  'w-full flex items-center gap-2 text-left text-[10px] px-2 py-1 rounded-lg transition-colors',
                  !typeFilter ? 'bg-brand-50 text-brand-700' : 'hover:bg-surface-900 text-surface-400',
                )}
              >
                <span className="w-2 h-2 rounded-full shrink-0 bg-surface-400" />
                <span>Все типы</span>
              </button>
              {nodeTypesInGraph.map(t => {
                const cfg = nodeTypeStyle(t)
                const count = apiNodes.filter(n => (n.type || 'Concept') === t).length
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTypeFilter(typeFilter === t ? '' : t)}
                    className={clsx(
                      'w-full flex items-center gap-2 text-left text-[10px] px-2 py-1 rounded-lg transition-colors',
                      typeFilter === t ? 'bg-brand-50 text-brand-700' : 'hover:bg-surface-900 text-surface-400',
                    )}
                  >
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: cfg.color }} />
                    <span className="truncate flex-1">{t}</span>
                    <span className="text-surface-500">{count}</span>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {relationTypesInGraph.length > 0 && (
          <div className="card p-3">
            <div className="label mb-2">Легенда связей</div>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {relationTypesInGraph.map(r => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRelationFilter(relationFilter === r ? '' : r)}
                  className={clsx(
                    'w-full flex items-center gap-2 text-left text-[10px] px-2 py-1 rounded-lg transition-colors',
                    relationFilter === r ? 'bg-brand-50 text-brand-700' : 'hover:bg-surface-900 text-surface-400',
                  )}
                >
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: relationColor(r) }} />
                  <span className="truncate">{relationMeta[r]?.label_ru || r}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {canEdit && (
          <div className="card p-3 space-y-2">
            <button type="button" className="btn-secondary w-full text-xs" onClick={() => setShowAdd(v => !v)}>
              <Plus size={11} /> {showAdd ? 'Скрыть' : 'Добавить связь'}
            </button>
            <button type="button" className="btn-ghost w-full text-xs" onClick={() => setShowHistory(v => !v)}>
              <History size={11} /> {showHistory ? 'Скрыть историю' : 'История правок'}
            </button>
            {showHistory && (
              <div className="max-h-40 overflow-y-auto space-y-1 text-[10px]">
                {graphEdits.length === 0 && <p className="text-surface-500 px-1">Правок пока нет</p>}
                {graphEdits.map(ed => (
                  <div key={ed.id} className="border border-surface-800 rounded-lg p-2">
                    <span className="font-semibold text-brand-600">{ed.action}</span>
                    {ed.comment && <p className="text-surface-400 mt-0.5">{ed.comment}</p>}
                    <p className="text-surface-500 mt-0.5">{ed.created_at?.slice(0, 16)}</p>
                  </div>
                ))}
              </div>
            )}
            {showAdd && (
              <form onSubmit={submitTriple} className="space-y-2">
                <input className="input text-xs py-1.5" placeholder="Субъект" required value={triple.subject}
                  onChange={e => setTriple(t => ({ ...t, subject: e.target.value }))} />
                <input className="input text-xs py-1.5" placeholder="Объект" required value={triple.object}
                  onChange={e => setTriple(t => ({ ...t, object: e.target.value }))} />
                <select className="input text-xs py-1.5" value={triple.relation}
                  onChange={e => setTriple(t => ({ ...t, relation: e.target.value }))}>
                  {Object.keys(relationMeta).map(r => (
                    <option key={r} value={r}>{relationMeta[r]?.label_ru || r}</option>
                  ))}
                </select>
                <button type="submit" className="btn-primary w-full text-xs" disabled={addBusy}>
                  {addBusy ? <Loader2 size={12} className="animate-spin-slow" /> : 'Сохранить'}
                </button>
              </form>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 card overflow-hidden relative" style={{ background: '#f7f4fd' }}>
        {error && (
          <div className="absolute top-3 left-3 z-10 card p-2 text-xs text-red-500 border-red-200">{error}</div>
        )}

        {!apiNodes.length && !error && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-surface-400 text-sm gap-3 z-10 px-6 text-center">
            <p>
              {entityMode
                ? `Узел «${centerEntity}» не найден.`
                : shouldFetchFull
                  ? 'Граф пуст. Синхронизируйте данные из SQLite.'
                  : 'Выберите источник, введите узел (например «медь») или загрузите весь граф.'}
            </p>
            {!shouldFetchFull && (
              <button type="button" className="btn-primary text-xs" onClick={() => setLoadFull(true)}>
                Загрузить весь граф
              </button>
            )}
            {canEdit && shouldFetchFull && (
              <button type="button" className="btn-primary text-xs" onClick={syncFromSqlite} disabled={addBusy}>
                {addBusy ? <Loader2 size={14} className="animate-spin-slow" /> : 'Синхронизировать из SQLite'}
              </button>
            )}
          </div>
        )}

        {rendering && filteredNodes.length > 0 && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#f7f4fd]/80 z-10 text-surface-400 text-sm gap-2">
            <Loader2 size={18} className="animate-spin-slow" />
            Инициализация графа…
          </div>
        )}

        <div className="absolute top-3 right-3 z-10 flex gap-1">
          {[
            [ZoomIn, () => canvasRef.current?.zoomIn()],
            [ZoomOut, () => canvasRef.current?.zoomOut()],
            [Maximize2, () => canvasRef.current?.fit()],
          ].map(([Icon, fn], i) => (
            <button key={i} type="button" onClick={fn}
              className="w-8 h-8 bg-white border border-surface-700 rounded-lg flex items-center justify-center hover:border-brand-300 shadow-card">
              <Icon size={13} className="text-surface-400" />
            </button>
          ))}
        </div>

        {(hoveredEdge || hovered) && (
          <div className="absolute bottom-3 left-3 z-10 card px-3 py-2.5 text-xs max-w-lg shadow-card pointer-events-none">
            {hoveredEdge ? (
              <EdgeFactCard edge={hoveredEdge} relationMeta={relationMeta} nodeById={nodeById} compact />
            ) : hovered && nodeById[hovered] ? (
              <>
                <span className="badge bg-brand-50 text-brand-600 border border-brand-100 text-[10px] mr-1">
                  {nodeById[hovered].type}
                </span>
                <span className="font-semibold text-surface-100">{nodeById[hovered].name}</span>
              </>
            ) : null}
          </div>
        )}

        {filteredNodes.length > 0 && (
          <VisGraphCanvas
            ref={canvasRef}
            nodes={filteredNodes}
            edges={filteredEdges}
            relationMeta={relationMeta}
            selectedNodeId={selected}
            selectedEdgeId={selectedEdgeId}
            showEdgeLabels={showAllLabels}
            onReady={() => setRendering(false)}
            onNodeSelect={(id) => selectNode(id)}
            onEdgeSelect={(edge) => selectEdge(edge)}
            onNodeHover={setHovered}
            onEdgeHover={setHoveredEdge}
            onBackgroundClick={() => { setSelected(null); setSelectedEdge(null) }}
          />
        )}
      </div>

      <div className={clsx('shrink-0 transition-all duration-300 overflow-hidden', panelOpen ? 'w-80' : 'w-0')}>
        {selectedEdge && (
          <div className="card h-full overflow-auto" style={{ width: '320px' }}>
            <div className="p-4 border-b border-surface-700 flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <GitBranch size={14} className="text-brand-600 shrink-0" />
                  <span
                    className="badge border text-[10px]"
                    style={{ color: relationColor(edgeRelation(selectedEdge)), borderColor: relationColor(edgeRelation(selectedEdge)), background: `${relationColor(edgeRelation(selectedEdge))}15` }}
                  >
                    {relationLabel(selectedEdge, relationMeta)}
                  </span>
                </div>
              </div>
              <button type="button" className="btn-ghost p-1" onClick={() => setSelectedEdge(null)}>
                <X size={14} />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <EdgeFactCard edge={selectedEdge} relationMeta={relationMeta} nodeById={nodeById} />
              <div className="rounded-xl border border-surface-700 p-3 bg-surface-900/50">
                <p className="label mb-1">От</p>
                <p className="text-sm font-semibold text-surface-100">
                  {selectedEdge.source_name || nodeById[selectedEdge.source]?.name}
                </p>
                <button type="button" className="text-xs text-brand-600 mt-2" onClick={() => selectNode(selectedEdge.source)}>
                  Выбрать узел →
                </button>
              </div>
              <div className="flex justify-center">
                <div className="px-3 py-1 rounded-full text-[10px] font-medium text-white"
                  style={{ background: relationColor(edgeRelation(selectedEdge)) }}>
                  {relationLabel(selectedEdge, relationMeta)}
                </div>
              </div>
              <div className="rounded-xl border border-surface-700 p-3 bg-surface-900/50">
                <p className="label mb-1">К</p>
                <p className="text-sm font-semibold text-surface-100">
                  {selectedEdge.target_name || nodeById[selectedEdge.target]?.name}
                </p>
                <button type="button" className="text-xs text-brand-600 mt-2" onClick={() => selectNode(selectedEdge.target)}>
                  Выбрать узел →
                </button>
              </div>

              {canEdit && selectedEdge.fact_id && edgeEdit && (
                <div className="border-t border-surface-700 pt-4 space-y-2">
                  <p className="label flex items-center gap-1"><Pencil size={11} /> Правка связи</p>
                  <input className="input text-xs py-1.5" value={edgeEdit.subject}
                    onChange={e => setEdgeEdit(v => ({ ...v, subject: e.target.value }))} />
                  <select className="input text-xs py-1.5" value={edgeEdit.relation}
                    onChange={e => setEdgeEdit(v => ({ ...v, relation: e.target.value }))}>
                    {Object.keys(relationMeta).map(r => (
                      <option key={r} value={r}>{relationMeta[r]?.label_ru || r}</option>
                    ))}
                  </select>
                  <input className="input text-xs py-1.5" value={edgeEdit.object}
                    onChange={e => setEdgeEdit(v => ({ ...v, object: e.target.value }))} />
                  <input className="input text-xs py-1.5" placeholder="Описание / комментарий к правке"
                    value={edgeEditComment} onChange={e => setEdgeEditComment(e.target.value)} />
                  <div className="flex gap-2">
                    <button type="button" className="btn-primary flex-1 text-xs" disabled={addBusy} onClick={saveEdgeEdit}>
                      {addBusy ? <Loader2 size={12} className="animate-spin-slow" /> : 'Сохранить'}
                    </button>
                    <button type="button" className="btn-ghost text-xs text-red-500" disabled={addBusy} onClick={removeEdge}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              )}

              {factVersions.length > 0 && (
                <div className="border-t border-surface-700 pt-3">
                  <p className="label mb-2">История версий ({factVersions.length})</p>
                  <div className="space-y-1 max-h-32 overflow-y-auto text-[10px]">
                    {factVersions.map(v => (
                      <div key={v.id || v.version} className="text-surface-400 border border-surface-800 rounded p-2">
                        v{v.version} · {v.created_at?.slice(0, 16) || '—'}
                        {v.change_reason && <span> · {v.change_reason}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {selNode && !selectedEdge && (
          <div className="card h-full overflow-auto" style={{ width: '320px' }}>
            <div className="p-4 border-b border-surface-700 flex items-start justify-between gap-2">
              <div>
                <span className="badge bg-brand-50 text-brand-600 border border-brand-100">{selNode.type}</span>
                <h3 className="text-sm font-bold text-surface-100 mt-2 leading-snug">{selNode.name}</h3>
                {selNode.aliases?.length > 0 && (
                  <p className="text-[10px] text-surface-400 mt-1">
                    Также: {selNode.aliases.join(', ')}
                  </p>
                )}
              </div>
              <button type="button" className="btn-ghost p-1" onClick={() => setSelected(null)}>
                <X size={14} />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <button type="button" className="btn-secondary w-full text-xs" onClick={() => applyCenter(selNode.name)}>
                <Network size={12} /> Центрировать подграф
              </button>
              <button type="button" className="btn-ghost w-full text-xs" onClick={() => canvasRef.current?.focusNode(selNode.id)}>
                Приблизить к узлу
              </button>
              <div>
                <div className="label mb-2">Связи ({connectedEdges.length})</div>
                <div className="space-y-2 max-h-[50vh] overflow-y-auto">
                  {connectedEdges.map((edge, i) => {
                    const outgoing = edge.source === selected
                    const otherId = outgoing ? edge.target : edge.source
                    const other = nodeById[otherId]
                    const color = relationColor(edgeRelation(edge))
                    return (
                      <button
                        key={edge.id || i}
                        type="button"
                        onClick={() => selectEdge(edge)}
                        className="w-full p-2.5 rounded-xl text-left border bg-white border-surface-700 hover:border-brand-300 transition-all group"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                          <span className="text-[10px] font-semibold" style={{ color }}>
                            {relationLabel(edge, relationMeta)}
                          </span>
                          <span className="text-[10px] text-surface-400 ml-auto">
                            {outgoing ? '→' : '←'}
                          </span>
                        </div>
                        <p className="text-xs font-medium text-surface-100 truncate group-hover:text-brand-700">
                          {other?.name}
                        </p>
                        {edgeFactText(edge) && (
                          <p className="text-[10px] text-surface-400 mt-1 line-clamp-2">
                            {edgeFactText(edge)}
                          </p>
                        )}
                      </button>
                    )
                  })}
                  {connectedEdges.length === 0 && (
                    <p className="text-xs text-surface-400">Нет связей в текущей выборке</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
