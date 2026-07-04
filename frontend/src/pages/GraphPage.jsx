import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Search, ZoomIn, ZoomOut, Maximize2, X, RotateCcw,
  Loader2, Network, Plus, GitBranch, Filter,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'
import VisGraphCanvas from '../graph/VisGraphCanvas'
import {
  RELATION_META_FALLBACK,
  relationLabel,
  relationDescription,
  relationColor,
  edgeKey,
} from '../graph/constants'

export default function GraphPage() {
  const { auth, user } = useAuth()
  const canEdit = ['analyst', 'project_manager', 'admin'].includes(user?.role)
  const [searchParams, setSearchParams] = useSearchParams()
  const centerEntity = searchParams.get('entity') || searchParams.get('entity_name') || ''

  const canvasRef = useRef(null)
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] })
  const [relationMeta, setRelationMeta] = useState(RELATION_META_FALLBACK)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [selectedEdge, setSelectedEdge] = useState(null)
  const [hovered, setHovered] = useState(null)
  const [hoveredEdge, setHoveredEdge] = useState(null)
  const [search, setSearch] = useState('')
  const [relationFilter, setRelationFilter] = useState('')
  const [showAllLabels, setShowAllLabels] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [addBusy, setAddBusy] = useState(false)
  const [triple, setTriple] = useState({
    subject: '', subject_type: 'Material', relation: 'related_to',
    object: '', object_type: 'Process', comment: '',
  })

  useEffect(() => {
    api.getOntology(auth).then(data => {
      if (data?.relation_meta) setRelationMeta({ ...RELATION_META_FALLBACK, ...data.relation_meta })
    }).catch(() => {})
  }, [auth])

  const apiNodes = graphData.nodes || []
  const apiEdges = graphData.edges || []

  const relationTypesInGraph = useMemo(() => {
    const s = new Set(apiEdges.map(e => e.relation).filter(Boolean))
    return [...s].sort()
  }, [apiEdges])

  const filteredNodes = useMemo(() =>
    apiNodes.filter(n =>
      !search || (n.name || '').toLowerCase().includes(search.toLowerCase()))
  , [apiNodes, search])

  const filteredIds = useMemo(() => new Set(filteredNodes.map(n => n.id)), [filteredNodes])

  const filteredEdges = useMemo(() =>
    apiEdges.filter(e => {
      if (!filteredIds.has(e.source) || !filteredIds.has(e.target)) return false
      if (relationFilter && e.relation !== relationFilter) return false
      return true
    })
  , [apiEdges, filteredIds, relationFilter])

  const connectedEdges = useMemo(() => {
    if (!selected) return []
    return filteredEdges.filter(e => e.source === selected || e.target === selected)
  }, [selected, filteredEdges])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api.getGraphView(auth, { limit: 200, entity_name: centerEntity || undefined })
      .then(data => { if (!cancelled) setGraphData(data) })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [auth, centerEntity])

  const reloadGraph = useCallback(() => {
    setLoading(true)
    setError('')
    return api.getGraphView(auth, { limit: 200, entity_name: centerEntity || undefined })
      .then(data => setGraphData(data))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [auth, centerEntity])

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

  const applyCenter = (name) => {
    if (name) setSearchParams({ entity: name })
    else setSearchParams({})
  }

  const selNode = apiNodes.find(n => n.id === selected)
  const nodeById = useMemo(() => Object.fromEntries(apiNodes.map(n => [n.id, n])), [apiNodes])
  const selectedEdgeId = selectedEdge ? edgeKey(selectedEdge) : null
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
              placeholder="Найти узел…"
              className="input pl-8 py-2 text-xs"
            />
          </div>
          {centerEntity && (
            <div className="mt-2 flex items-center gap-1 text-[10px] text-brand-600 bg-brand-50 rounded-lg px-2 py-1">
              <Network size={10} />
              <span className="truncate flex-1">Центр: {centerEntity}</span>
              <button type="button" onClick={() => applyCenter('')}><X size={10} /></button>
            </div>
          )}
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
            Колёсико — зум, перетаскивание — панорама. Узел можно тащить мышью.
          </p>
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
          </div>
          <button type="button" onClick={() => canvasRef.current?.stabilize()} className="btn-secondary w-full text-xs">
            <RotateCcw size={11} /> Пересчитать layout
          </button>
        </div>

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
          <div className="card p-3">
            <button type="button" className="btn-secondary w-full text-xs mb-2" onClick={() => setShowAdd(v => !v)}>
              <Plus size={11} /> {showAdd ? 'Скрыть' : 'Добавить связь'}
            </button>
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

      <div className="flex-1 card overflow-hidden relative" style={{ background: 'linear-gradient(160deg, #f7f4fd 0%, #ede8f8 100%)' }}>
        {error && (
          <div className="absolute top-3 left-3 z-10 card p-2 text-xs text-red-500 border-red-200">{error}</div>
        )}
        {!apiNodes.length && !error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-surface-400 text-sm gap-3 z-10">
            <p>Граф пуст в Neo4j. Данные могут быть только в SQLite.</p>
            {canEdit && (
              <button type="button" className="btn-primary text-xs" onClick={syncFromSqlite} disabled={addBusy}>
                {addBusy ? <Loader2 size={14} className="animate-spin-slow" /> : 'Синхронизировать из SQLite'}
              </button>
            )}
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
          <div className="absolute bottom-3 left-3 z-10 card px-3 py-2.5 text-xs max-w-md shadow-card pointer-events-none">
            {hoveredEdge ? (
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span
                    className="badge border text-[10px] shrink-0"
                    style={{
                      color: relationColor(hoveredEdge.relation),
                      borderColor: relationColor(hoveredEdge.relation),
                      background: `${relationColor(hoveredEdge.relation)}12`,
                    }}
                  >
                    {relationLabel(hoveredEdge, relationMeta)}
                  </span>
                  <span className="text-surface-300 font-medium">
                    {(hoveredEdge.source_name || nodeById[hoveredEdge.source]?.name || '?')}
                    <span className="text-surface-400 mx-1">→</span>
                    {(hoveredEdge.target_name || nodeById[hoveredEdge.target]?.name || '?')}
                  </span>
                </div>
                {relationDescription(hoveredEdge, relationMeta) && (
                  <p className="text-[11px] text-surface-400 leading-snug">
                    {relationDescription(hoveredEdge, relationMeta)}
                  </p>
                )}
              </div>
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
              <div>
                <div className="flex items-center gap-2">
                  <GitBranch size={14} className="text-brand-600" />
                  <span
                    className="badge border text-[10px]"
                    style={{ color: relationColor(selectedEdge.relation), borderColor: relationColor(selectedEdge.relation), background: `${relationColor(selectedEdge.relation)}15` }}
                  >
                    {relationLabel(selectedEdge, relationMeta)}
                  </span>
                </div>
                <p className="text-xs text-surface-400 mt-2 leading-relaxed">
                  {relationDescription(selectedEdge, relationMeta)}
                </p>
              </div>
              <button type="button" className="btn-ghost p-1" onClick={() => setSelectedEdge(null)}>
                <X size={14} />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div className="rounded-xl border border-surface-700 p-3 bg-surface-900/50">
                <p className="label mb-1">От</p>
                <p className="text-sm font-semibold text-surface-100">
                  {selectedEdge.source_name || nodeById[selectedEdge.source]?.name}
                </p>
                <p className="text-[10px] text-surface-400 mt-0.5">
                  {selectedEdge.source_type || nodeById[selectedEdge.source]?.type}
                </p>
                <button type="button" className="text-xs text-brand-600 mt-2" onClick={() => selectNode(selectedEdge.source)}>
                  Выбрать узел →
                </button>
              </div>
              <div className="flex justify-center">
                <div className="px-3 py-1 rounded-full text-[10px] font-medium text-white"
                  style={{ background: relationColor(selectedEdge.relation) }}>
                  {relationLabel(selectedEdge, relationMeta)}
                </div>
              </div>
              <div className="rounded-xl border border-surface-700 p-3 bg-surface-900/50">
                <p className="label mb-1">К</p>
                <p className="text-sm font-semibold text-surface-100">
                  {selectedEdge.target_name || nodeById[selectedEdge.target]?.name}
                </p>
                <p className="text-[10px] text-surface-400 mt-0.5">
                  {selectedEdge.target_type || nodeById[selectedEdge.target]?.type}
                </p>
                <button type="button" className="text-xs text-brand-600 mt-2" onClick={() => selectNode(selectedEdge.target)}>
                  Выбрать узел →
                </button>
              </div>
            </div>
          </div>
        )}

        {selNode && !selectedEdge && (
          <div className="card h-full overflow-auto" style={{ width: '320px' }}>
            <div className="p-4 border-b border-surface-700 flex items-start justify-between gap-2">
              <div>
                <span className="badge bg-brand-50 text-brand-600 border border-brand-100">{selNode.type}</span>
                <h3 className="text-sm font-bold text-surface-100 mt-2 leading-snug">{selNode.name}</h3>
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
                    const color = relationColor(edge.relation)
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
                        {relationDescription(edge, relationMeta) && (
                          <p className="text-[10px] text-surface-400 mt-1 line-clamp-2">
                            {relationDescription(edge, relationMeta)}
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
