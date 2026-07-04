import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Search, ZoomIn, ZoomOut, Maximize2, ChevronRight, X, RotateCcw,
  Loader2, Network, Plus, GitBranch, Filter,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'
import {
  RELATION_META_FALLBACK,
  relationLabel,
  relationDescription,
  relationColor,
  edgeGeometry,
} from '../graph/constants'

const TYPE_CFG = {
  Process:     { from: '#8b5cf6', to: '#6d28d9', glow: '#8b5cf6' },
  Material:    { from: '#10b981', to: '#047857', glow: '#10b981' },
  Equipment:   { from: '#f59e0b', to: '#b45309', glow: '#f59e0b' },
  Property:    { from: '#0ea5e9', to: '#0369a1', glow: '#0ea5e9' },
  Parameter:   { from: '#06b6d4', to: '#0e7490', glow: '#06b6d4' },
  Metric:      { from: '#14b8a6', to: '#0f766e', glow: '#14b8a6' },
  Expert:      { from: '#f472b6', to: '#be185d', glow: '#f472b6' },
  Publication: { from: '#fbbf24', to: '#92400e', glow: '#fbbf24' },
  Facility:    { from: '#818cf8', to: '#3730a3', glow: '#818cf8' },
  Concept:     { from: '#a78bfa', to: '#6d28d9', glow: '#a78bfa' },
  Document:    { from: '#64748b', to: '#334155', glow: '#64748b' },
  Geography:   { from: '#22c55e', to: '#15803d', glow: '#22c55e' },
  Regulation:  { from: '#ef4444', to: '#b91c1c', glow: '#ef4444' },
  Product:     { from: '#ec4899', to: '#9d174d', glow: '#ec4899' },
  Experiment:  { from: '#6366f1', to: '#4338ca', glow: '#6366f1' },
}

const DEFAULT_CFG = { from: '#5302e0', to: '#4200b5', glow: '#5302e0' }

const SIM_W = 820
const SIM_H = 520

function buildDeg(edges) {
  const d = {}
  edges.forEach(e => {
    d[e.source] = (d[e.source] || 0) + 1
    d[e.target] = (d[e.target] || 0) + 1
  })
  return d
}

function initSimNodes(nodes, edges) {
  const deg = buildDeg(edges)
  return nodes.map((n, i) => {
    const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2
    const r = 150 + (Math.random() - 0.5) * 60
    return {
      id: n.id,
      label: n.name,
      type: n.type || 'Concept',
      degree: deg[n.id] || 1,
      x: SIM_W / 2 + Math.cos(angle) * r,
      y: SIM_H / 2 + Math.sin(angle) * r,
      vx: 0, vy: 0, fx: null, fy: null, ax: 0, ay: 0,
    }
  })
}

function simTick(nodes, edges, alpha) {
  const REP = 5600, LINK = 0.16, REST = 130, GRAV = 0.032, DAMP = 0.82
  const cx = SIM_W / 2, cy = SIM_H / 2
  const map = {}
  nodes.forEach(n => { map[n.id] = n; n.ax = 0; n.ay = 0 })

  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j]
      const dx = b.x - a.x, dy = b.y - a.y
      const d2 = dx * dx + dy * dy + 0.1
      const d = Math.sqrt(d2)
      const f = (REP * alpha) / d2
      const nx = dx / d, ny = dy / d
      a.ax -= f * nx; a.ay -= f * ny
      b.ax += f * nx; b.ay += f * ny
    }
  }

  edges.forEach(e => {
    const a = map[e.source], b = map[e.target]
    if (!a || !b) return
    const dx = b.x - a.x, dy = b.y - a.y
    const d = Math.sqrt(dx * dx + dy * dy) || 1
    const f = (d - REST) * LINK * alpha
    const nx = dx / d, ny = dy / d
    a.ax += f * nx; a.ay += f * ny
    b.ax -= f * nx; b.ay -= f * ny
  })

  nodes.forEach(n => {
    n.ax += (cx - n.x) * GRAV * alpha
    n.ay += (cy - n.y) * GRAV * alpha
  })

  nodes.forEach(n => {
    if (n.fx !== null) { n.x = n.fx; n.y = n.fy; n.vx = 0; n.vy = 0; return }
    n.vx = (n.vx + n.ax) * DAMP
    n.vy = (n.vy + n.ay) * DAMP
    n.x = Math.max(28, Math.min(SIM_W - 28, n.x + n.vx))
    n.y = Math.max(28, Math.min(SIM_H - 28, n.y + n.vy))
  })
}

function EdgeLabel({ x, y, text, color, scale, highlight }) {
  const fs = Math.max(9, Math.min(12, 10 * scale))
  const pad = 3 * scale
  const w = text.length * fs * 0.55 + pad * 2
  const h = fs + pad * 2
  return (
    <g transform={`translate(${x}, ${y})`} style={{ pointerEvents: 'none' }}>
      <rect
        x={-w / 2} y={-h / 2} width={w} height={h} rx={h / 2}
        fill={highlight ? '#fff' : 'rgba(255,255,255,0.92)'}
        stroke={highlight ? color : '#e2d9f3'}
        strokeWidth={highlight ? 1.2 : 0.6}
      />
      <text
        textAnchor="middle" dominantBaseline="central"
        fontSize={fs} fontWeight={highlight ? 600 : 500}
        fill={highlight ? color : '#5b4d7a'}
      >
        {text}
      </text>
    </g>
  )
}

export default function GraphPage() {
  const { auth, user } = useAuth()
  const canEdit = ['analyst', 'project_manager', 'admin'].includes(user?.role)
  const [searchParams, setSearchParams] = useSearchParams()
  const centerEntity = searchParams.get('entity') || searchParams.get('entity_name') || ''

  const [, forceRender] = useState(0)
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
  const [showAllLabels, setShowAllLabels] = useState(true)
  const [xform, setXform] = useState({ x: 0, y: 0, s: 1 })
  const [isPan, setIsPan] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [addBusy, setAddBusy] = useState(false)
  const [triple, setTriple] = useState({
    subject: '', subject_type: 'Material', relation: 'related_to',
    object: '', object_type: 'Process', comment: '',
  })

  const nodesRef = useRef([])
  const rafRef = useRef(null)
  const alphaRef = useRef(1)
  const dragRef = useRef(null)
  const panRef = useRef(null)
  const xformRef = useRef({ x: 0, y: 0, s: 1 })
  const svgRef = useRef(null)

  useEffect(() => { xformRef.current = xform }, [xform])

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

  const connectedIds = useMemo(() => {
    if (!selected && !selectedEdge) return null
    const s = new Set()
    if (selected) {
      filteredEdges.forEach(e => {
        if (e.source === selected) s.add(e.target)
        if (e.target === selected) s.add(e.source)
      })
    }
    if (selectedEdge) {
      s.add(selectedEdge.source)
      s.add(selectedEdge.target)
    }
    return s
  }, [selected, selectedEdge, filteredEdges])

  const connectedEdges = useMemo(() => {
    if (!selected) return []
    return filteredEdges.filter(e => e.source === selected || e.target === selected)
  }, [selected, filteredEdges])

  const startSim = useCallback((edges) => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    const loop = () => {
      if (alphaRef.current < 0.004) { forceRender(n => n + 1); return }
      simTick(nodesRef.current, edges, alphaRef.current)
      alphaRef.current *= 0.97
      forceRender(n => n + 1)
      rafRef.current = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
  }, [])

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

  useEffect(() => {
    if (!apiNodes.length) return
    nodesRef.current = initSimNodes(filteredNodes.length ? filteredNodes : apiNodes, filteredEdges.length ? filteredEdges : apiEdges)
    alphaRef.current = 1
    startSim(filteredEdges.length ? filteredEdges : apiEdges)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [apiNodes, apiEdges, filteredNodes, filteredEdges, startSim])

  const fitToView = useCallback(() => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const scale = Math.min(rect.width / SIM_W, rect.height / SIM_H) * 1.35
    const t = { s: scale, x: (rect.width - SIM_W * scale) / 2, y: (rect.height - SIM_H * scale) / 2 }
    xformRef.current = t
    setXform(t)
  }, [])

  useEffect(() => {
    if (!loading) fitToView()
    window.addEventListener('resize', fitToView)
    return () => window.removeEventListener('resize', fitToView)
  }, [loading, fitToView])

  const reheat = () => { alphaRef.current = 0.8; startSim(filteredEdges) }

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
      const data = await api.getGraphView(auth, { limit: 200, entity_name: centerEntity || undefined })
      setGraphData(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setAddBusy(false)
    }
  }

  const toSim = useCallback((cx, cy) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    const t = xformRef.current
    return { x: (cx - rect.left - t.x) / t.s, y: (cy - rect.top - t.y) / t.s }
  }, [])

  const selectNode = (id) => {
    setSelected(id)
    setSelectedEdge(null)
  }

  const selectEdge = (edge) => {
    setSelectedEdge(edge)
    setSelected(null)
  }

  const onNodeDown = useCallback((e, id) => {
    e.stopPropagation()
    const pt = toSim(e.clientX, e.clientY)
    const node = nodesRef.current.find(n => n.id === id)
    if (!node) return
    node.fx = node.x; node.fy = node.y
    dragRef.current = { id, ox: pt.x - node.x, oy: pt.y - node.y, moved: false }
    alphaRef.current = Math.max(alphaRef.current, 0.15)
    startSim(filteredEdges)
  }, [toSim, filteredEdges, startSim])

  const onBgDown = useCallback((e) => {
    if (e.button !== 0) return
    panRef.current = { sx: e.clientX, sy: e.clientY, tx: xformRef.current.x, ty: xformRef.current.y }
    setIsPan(true)
  }, [])

  const onMove = useCallback((e) => {
    if (dragRef.current) {
      const pt = toSim(e.clientX, e.clientY)
      const node = nodesRef.current.find(n => n.id === dragRef.current.id)
      if (node) {
        node.fx = pt.x - dragRef.current.ox
        node.fy = pt.y - dragRef.current.oy
        node.x = node.fx; node.y = node.fy
        dragRef.current.moved = true
        forceRender(n => n + 1)
      }
    } else if (panRef.current) {
      const dx = e.clientX - panRef.current.sx
      const dy = e.clientY - panRef.current.sy
      const t = { ...xformRef.current, x: panRef.current.tx + dx, y: panRef.current.ty + dy }
      xformRef.current = t
      setXform(t)
    }
  }, [toSim])

  const onUp = useCallback(() => {
    if (dragRef.current) {
      const { id, moved } = dragRef.current
      const node = nodesRef.current.find(n => n.id === id)
      if (node) { node.fx = null; node.fy = null }
      if (!moved) selectNode(selected === id ? null : id)
      dragRef.current = null
    }
    panRef.current = null
    setIsPan(false)
  }, [selected])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (e) => {
      e.preventDefault()
      const f = e.deltaY < 0 ? 1.12 : 1 / 1.12
      const rect = svg.getBoundingClientRect()
      const mx = e.clientX - rect.left, my = e.clientY - rect.top
      setXform(t => {
        const ns = Math.max(0.12, Math.min(6, t.s * f))
        const sf = ns / t.s
        return { x: mx - sf * (mx - t.x), y: my - sf * (my - t.y), s: ns }
      })
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [])

  const getPos = (id) => nodesRef.current.find(n => n.id === id) || null
  const getR = (id) => {
    const n = nodesRef.current.find(nn => nn.id === id)
    return Math.min(15, 5 + (n?.degree || 1) * 1.7)
  }
  const invS = 1 / xform.s
  const showLabels = showAllLabels || xform.s > 0.45

  const selNode = apiNodes.find(n => n.id === selected)
  const nodeById = useMemo(() => Object.fromEntries(apiNodes.map(n => [n.id, n])), [apiNodes])

  const applyCenter = (name) => {
    if (name) setSearchParams({ entity: name })
    else setSearchParams({})
  }

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
            Подписи связей
          </label>
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
          <button type="button" onClick={reheat} className="btn-secondary w-full text-xs">
            <RotateCcw size={11} /> Пересчитать
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
        {!apiNodes.length && !error && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-surface-400 text-sm gap-3">
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
            [ZoomIn, () => setXform(t => ({ ...t, s: Math.min(6, t.s * 1.2) }))],
            [ZoomOut, () => setXform(t => ({ ...t, s: Math.max(0.12, t.s / 1.2) }))],
            [Maximize2, fitToView],
          ].map(([Icon, fn], i) => (
            <button key={i} type="button" onClick={fn}
              className="w-8 h-8 bg-white border border-surface-700 rounded-lg flex items-center justify-center hover:border-brand-300 shadow-card">
              <Icon size={13} className="text-surface-400" />
            </button>
          ))}
        </div>

        {(hoveredEdge || hovered) && !dragRef.current && (
          <div className="absolute bottom-3 left-3 z-10 card px-3 py-2 text-xs max-w-sm shadow-card pointer-events-none">
            {hoveredEdge ? (
              <>
                <span className="font-semibold text-brand-600">{relationLabel(hoveredEdge, relationMeta)}</span>
                <span className="text-surface-400 mx-1">·</span>
                <span className="text-surface-300">
                  {(hoveredEdge.source_name || nodeById[hoveredEdge.source]?.name || '?')}
                  {' → '}
                  {(hoveredEdge.target_name || nodeById[hoveredEdge.target]?.name || '?')}
                </span>
              </>
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

        <svg ref={svgRef} width="100%" height="100%"
          className={clsx('select-none', isPan ? 'cursor-grabbing' : 'cursor-grab')}
          onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
          <defs>
            <marker id="arrow-default" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L0,6 L8,3 z" fill="#94a3b8" />
            </marker>
            {relationTypesInGraph.map(r => (
              <marker
                key={r}
                id={`arrow-${r}`}
                markerWidth="8" markerHeight="8" refX="7" refY="3"
                orient="auto" markerUnits="strokeWidth"
              >
                <path d="M0,0 L0,6 L8,3 z" fill={relationColor(r)} />
              </marker>
            ))}
          </defs>
          <rect width="100%" height="100%" fill="transparent" onMouseDown={onBgDown} />
          <g transform={`translate(${xform.x},${xform.y}) scale(${xform.s})`}>
            {filteredEdges.map((edge, i) => {
              const s = getPos(edge.source)
              const t = getPos(edge.target)
              if (!s || !t) return null
              const geo = edgeGeometry(s, t, getR(edge.source), getR(edge.target), invS, i)
              const edgeId = edge.id || `${edge.source}:${edge.relation}:${edge.target}`
              const isSel = selectedEdge?.id === edgeId || selectedEdge === edge
                || (selectedEdge?.source === edge.source && selectedEdge?.target === edge.target && selectedEdge?.relation === edge.relation)
              const isHov = hoveredEdge?.id === edgeId || hoveredEdge === edge
              const isConn = (selected && (edge.source === selected || edge.target === selected))
                || (selectedEdge && (edge.source === selectedEdge.source && edge.target === selectedEdge.target))
              const dim = (selected || selectedEdge) && !isConn && !isSel
              const color = relationColor(edge.relation)
              const label = relationLabel(edge, relationMeta)
              const strokeW = (isSel || isHov ? 2.2 : isConn ? 1.8 : 1.2) * invS

              return (
                <g
                  key={edgeId}
                  style={{ opacity: dim ? 0.07 : isSel || isHov ? 1 : 0.75 }}
                  onMouseEnter={() => setHoveredEdge(edge)}
                  onMouseLeave={() => setHoveredEdge(null)}
                  onClick={(e) => { e.stopPropagation(); selectEdge(edge) }}
                  className="cursor-pointer"
                >
                  <path
                    d={geo.path}
                    fill="none"
                    stroke="transparent"
                    strokeWidth={14 * invS}
                  />
                  <path
                    d={geo.path}
                    fill="none"
                    stroke={isSel || isHov ? color : isConn ? '#5302e0' : color}
                    strokeWidth={strokeW}
                    strokeOpacity={isSel || isHov ? 1 : 0.85}
                    markerEnd={`url(#arrow-${relationTypesInGraph.includes(edge.relation) ? edge.relation : 'default'})`}
                  />
                  {showLabels && (isSel || isHov || isConn || showAllLabels) && label && (
                    <EdgeLabel
                      x={geo.lx} y={geo.ly}
                      text={label}
                      color={color}
                      scale={invS}
                      highlight={isSel || isHov}
                    />
                  )}
                </g>
              )
            })}

            {filteredNodes.map(node => {
              const p = getPos(node.id)
              if (!p) return null
              const cfg = TYPE_CFG[node.type] || DEFAULT_CFG
              const isSel = selected === node.id
              const isConn = connectedIds?.has(node.id)
              const dim = (selected || selectedEdge) && !isSel && !isConn
              const r = getR(node.id)
              const label = (node.name || '').length > 28 ? node.name.slice(0, 27) + '…' : node.name
              return (
                <g
                  key={node.id}
                  transform={`translate(${p.x},${p.y}) scale(${invS})`}
                  style={{ opacity: dim ? 0.12 : 1, cursor: 'pointer' }}
                  onMouseDown={e => onNodeDown(e, node.id)}
                  onMouseEnter={() => setHovered(node.id)}
                  onMouseLeave={() => setHovered(null)}
                >
                  {isSel && <circle r={r + 5} fill="none" stroke="#5302e0" strokeWidth="2" opacity={0.5} />}
                  {isConn && !isSel && <circle r={r + 3} fill="none" stroke={cfg.glow} strokeWidth="1.5" opacity={0.6} />}
                  <circle
                    r={r}
                    fill={cfg.glow}
                    stroke={hovered === node.id || isSel ? 'white' : 'rgba(255,255,255,0.4)'}
                    strokeWidth={hovered === node.id || isSel ? 2 : 1}
                  />
                  <text
                    x={r + 7} dominantBaseline="middle"
                    fontSize={isSel ? 12 : 11}
                    fontWeight={isSel ? 700 : 500}
                    fill={isSel ? '#5302e0' : '#3a2a5c'}
                    style={{ pointerEvents: 'none' }}
                  >
                    {label}
                  </text>
                </g>
              )
            })}
          </g>
        </svg>
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
              <p className="text-[10px] text-surface-500 font-mono">{selectedEdge.relation}</p>
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
                          <span
                            className="w-2 h-2 rounded-full shrink-0"
                            style={{ background: color }}
                          />
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
