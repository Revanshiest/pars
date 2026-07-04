import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search, ZoomIn, ZoomOut, Maximize2, ChevronRight, X, RotateCcw, Loader2, Network } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'

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

const SIM_W = 960
const SIM_H = 600

function normalizeLayout(nodes, pad = 56) {
  if (nodes.length < 2) return
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  nodes.forEach(n => {
    minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x)
    minY = Math.min(minY, n.y); maxY = Math.max(maxY, n.y)
  })
  const w = maxX - minX || 1
  const h = maxY - minY || 1
  const scale = Math.min((SIM_W - pad * 2) / w, (SIM_H - pad * 2) / h, 1.8)
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  nodes.forEach(n => {
    n.x = SIM_W / 2 + (n.x - cx) * scale
    n.y = SIM_H / 2 + (n.y - cy) * scale
    n.vx = 0
    n.vy = 0
  })
}

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
  const spread = Math.min(SIM_W, SIM_H) * (0.28 + Math.min(nodes.length, 120) / 400)
  return nodes.map((n, i) => {
    const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2 + (Math.random() - 0.5) * 0.4
    const r = spread * (0.5 + Math.random() * 0.5)
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
  const REP = 4200, LINK = 0.14, REST = 110 + Math.min(nodes.length, 80), GRAV = 0.07, DAMP = 0.84
  const margin = 40
  const map = {}
  nodes.forEach(n => { map[n.id] = n; n.ax = 0; n.ay = 0 })
  const cx = SIM_W / 2, cy = SIM_H / 2

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
    n.x += n.vx
    n.y += n.vy
    if (n.x < margin) { n.x = margin; n.vx *= -0.25 }
    if (n.x > SIM_W - margin) { n.x = SIM_W - margin; n.vx *= -0.25 }
    if (n.y < margin) { n.y = margin; n.vy *= -0.25 }
    if (n.y > SIM_H - margin) { n.y = SIM_H - margin; n.vy *= -0.25 }
  })
}

export default function GraphPage() {
  const { auth } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const centerEntity = searchParams.get('entity') || searchParams.get('entity_name') || ''
  const sourceDoc = searchParams.get('source') || ''

  const [, forceRender] = useState(0)
  const [graphData, setGraphData] = useState({ nodes: [], edges: [], documents: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [hovered, setHovered] = useState(null)
  const [search, setSearch] = useState(centerEntity)
  const [viewMode, setViewMode] = useState('canvas')
  const [htmlBlobUrl, setHtmlBlobUrl] = useState(null)
  const [htmlLoading, setHtmlLoading] = useState(false)
  const [xform, setXform] = useState({ x: 0, y: 0, s: 1 })
  const [isPan, setIsPan] = useState(false)

  const nodesRef = useRef([])
  const rafRef = useRef(null)
  const alphaRef = useRef(1)
  const dragRef = useRef(null)
  const panRef = useRef(null)
  const xformRef = useRef({ x: 0, y: 0, s: 1 })
  const svgRef = useRef(null)

  useEffect(() => { xformRef.current = xform }, [xform])

  const applyCenter = useCallback((name) => {
    const p = {}
    if (name) p.entity = name
    if (sourceDoc) p.source = sourceDoc
    setSearchParams(p)
  }, [sourceDoc, setSearchParams])

  useEffect(() => {
    setSearch(centerEntity)
  }, [centerEntity])

  // Авто-загрузка ego-графа при вводе
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

  const displayNodes = apiNodes
  const displayEdges = apiEdges

  const connectedIds = useMemo(() => {
    if (!selected) return null
    const s = new Set()
    displayEdges.forEach(e => {
      if (e.source === selected) s.add(e.target)
      if (e.target === selected) s.add(e.source)
    })
    return s
  }, [selected, displayEdges])

  const connectedEdges = useMemo(() =>
    selected ? displayEdges.filter(e => e.source === selected || e.target === selected) : []
  , [selected, displayEdges])

  const startSim = useCallback((edges) => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    const loop = () => {
      if (alphaRef.current < 0.004) {
        normalizeLayout(nodesRef.current)
        forceRender(n => n + 1)
        return
      }
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
    api.getGraphView(auth, {
      limit: 150,
      entity_name: centerEntity || undefined,
      source_document: sourceDoc || undefined,
    })
      .then(data => { if (!cancelled) setGraphData(data) })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [auth, centerEntity, sourceDoc])

  useEffect(() => {
    if (viewMode !== 'html') return undefined
    let cancelled = false
    setHtmlLoading(true)
    setError('')
    api.getGraphHtml(auth, {
      limit: 500,
      entity_name: centerEntity || undefined,
      source_document: sourceDoc || undefined,
    })
      .then(html => {
        if (cancelled) return
        const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }))
        setHtmlBlobUrl(prev => {
          if (prev) URL.revokeObjectURL(prev)
          return url
        })
      })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setHtmlLoading(false) })
    return () => {
      cancelled = true
      setHtmlBlobUrl(prev => {
        if (prev) URL.revokeObjectURL(prev)
        return null
      })
    }
  }, [auth, centerEntity, sourceDoc, viewMode])

  useEffect(() => {
    if (viewMode !== 'canvas' || !apiNodes.length) return
    nodesRef.current = initSimNodes(displayNodes.length ? displayNodes : apiNodes, displayEdges.length ? displayEdges : apiEdges)
    alphaRef.current = 1
    startSim(displayEdges.length ? displayEdges : apiEdges)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [viewMode, apiNodes, apiEdges, displayNodes, displayEdges, startSim])

  const fitToView = useCallback(() => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const scale = Math.min(rect.width / SIM_W, rect.height / SIM_H) * 1.35
    const t = {
      s: scale,
      x: (rect.width - SIM_W * scale) / 2,
      y: (rect.height - SIM_H * scale) / 2,
    }
    xformRef.current = t
    setXform(t)
  }, [])

  useEffect(() => {
    if (!loading) fitToView()
    window.addEventListener('resize', fitToView)
    return () => window.removeEventListener('resize', fitToView)
  }, [loading, fitToView])

  const reheat = () => { alphaRef.current = 0.8; startSim(displayEdges); setTimeout(() => normalizeLayout(nodesRef.current), 1200) }

  const toSim = useCallback((cx, cy) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    const t = xformRef.current
    return { x: (cx - rect.left - t.x) / t.s, y: (cy - rect.top - t.y) / t.s }
  }, [])

  const onNodeDown = useCallback((e, id) => {
    e.stopPropagation()
    const pt = toSim(e.clientX, e.clientY)
    const node = nodesRef.current.find(n => n.id === id)
    if (!node) return
    node.fx = node.x; node.fy = node.y
    dragRef.current = { id, ox: pt.x - node.x, oy: pt.y - node.y, moved: false }
    alphaRef.current = Math.max(alphaRef.current, 0.15)
    startSim(displayEdges)
  }, [toSim, displayEdges, startSim])

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
      if (!moved) setSelected(s => s === id ? null : id)
      dragRef.current = null
    }
    panRef.current = null
    setIsPan(false)
  }, [])

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

  const getPos = (id) => {
    const n = nodesRef.current.find(n => n.id === id)
    return n ? { x: n.x, y: n.y } : null
  }
  const getR = (id) => {
    const n = nodesRef.current.find(n => n.id === id)
    return Math.min(15, 5 + (n?.degree || 1) * 1.7)
  }
  const invS = 1 / xform.s

  const selNode = apiNodes.find(n => n.id === selected)
  const nodeById = useMemo(() => Object.fromEntries(apiNodes.map(n => [n.id, n])), [apiNodes])

  const submitSearch = () => {
    const q = search.trim()
    applyCenter(q)
  }

  const applySource = (doc) => {
    const p = {}
    if (centerEntity) p.entity = centerEntity
    if (doc) p.source = doc
    setSearchParams(p)
  }

  const documents = graphData.documents || []

  if (loading && viewMode === 'canvas') {
    return (
      <div className="flex items-center justify-center h-96 text-surface-400 gap-2">
        <Loader2 size={20} className="animate-spin-slow" />
        Загрузка графа…
      </div>
    )
  }

  return (
    <div className="h-full flex gap-4" style={{ height: 'calc(100vh - 8rem)' }}>
      <div className="w-60 shrink-0 flex flex-col gap-3">
        <div className="card p-3">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-2.5 text-surface-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); submitSearch() } }}
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
          <div className="flex gap-1">
            <button
              type="button"
              className={clsx('flex-1 text-xs py-1.5 rounded-lg border', viewMode === 'canvas' ? 'bg-brand-600 text-white border-brand-600' : 'border-surface-700')}
              onClick={() => setViewMode('canvas')}
            >
              Обзор (SVG)
            </button>
            <button
              type="button"
              className={clsx('flex-1 text-xs py-1.5 rounded-lg border', viewMode === 'html' ? 'bg-brand-600 text-white border-brand-600' : 'border-surface-700')}
              onClick={() => setViewMode('html')}
            >
              HTML (PyVis)
            </button>
          </div>
        </div>

        <div className="card p-3">
          <div className="grid grid-cols-2 gap-2 mb-2">
            <div className="text-center bg-brand-50 rounded-xl py-2">
              <div className="text-xl font-black text-brand-600">{displayNodes.length}</div>
              <div className="text-[10px] text-brand-400">узлов</div>
            </div>
            <div className="text-center bg-surface-900 rounded-xl py-2">
              <div className="text-xl font-black text-surface-200">{displayEdges.length}</div>
              <div className="text-[10px] text-surface-400">связей</div>
            </div>
          </div>
          <p className="text-xs text-surface-400 mt-2">
            {entityMode
              ? `Центр «${centerEntity}» — до 10 связей.`
              : 'Обзор до 150 узлов. Введите термин — связи загрузятся автоматически.'}
          </p>
          <button type="button" onClick={reheat} className="btn-secondary w-full text-xs mt-2">
            <RotateCcw size={11} /> Пересчитать
          </button>
        </div>
      </div>

      <div className="flex-1 card overflow-hidden relative" style={{ background: viewMode === 'html' ? '#222' : '#f7f4fd' }}>
        {error && (
          <div className="absolute top-3 left-3 z-10 card p-2 text-xs text-red-500 border-red-200">{error}</div>
        )}

        {viewMode === 'html' ? (
          htmlLoading ? (
            <div className="absolute inset-0 flex items-center justify-center text-surface-400 gap-2">
              <Loader2 size={20} className="animate-spin-slow" />
              Генерация HTML-графа…
            </div>
          ) : htmlBlobUrl ? (
            <iframe
              title="Knowledge graph"
              src={htmlBlobUrl}
              className="w-full h-full border-0"
              sandbox="allow-scripts allow-same-origin"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-surface-400 text-sm">
              Нет данных для визуализации
            </div>
          )
        ) : (
          <>
        {!apiNodes.length && !error && (
          <div className="absolute inset-0 flex items-center justify-center text-surface-400 text-sm text-center px-6">
            {entityMode
              ? `Узел «${centerEntity}» не найден. Попробуйте другое написание или снимите фильтр источника.`
              : 'Граф пуст. Загрузите документы или выберите источник «schlesinger».'}
          </div>
        )}

        <div className="absolute top-3 right-3 z-10 flex gap-1">
          {[
            [ZoomIn, () => setXform(t => ({ ...t, s: Math.min(6, t.s * 1.2) }))],
            [ZoomOut, () => setXform(t => ({ ...t, s: Math.max(0.12, t.s / 1.2) }))],
            [Maximize2, fitToView],
          ].map(([Icon, fn], i) => (
            <button key={i} type="button" onClick={fn}
              className="w-8 h-8 bg-white border border-surface-700 rounded-lg flex items-center justify-center hover:border-brand-300">
              <Icon size={13} className="text-surface-400" />
            </button>
          ))}
        </div>

        <svg ref={svgRef} width="100%" height="100%"
          className={clsx('select-none', isPan ? 'cursor-grabbing' : 'cursor-grab')}
          onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
          <rect width="100%" height="100%" fill="#f7f4fd" onMouseDown={onBgDown} />
          <g transform={`translate(${xform.x},${xform.y}) scale(${xform.s})`}>
            {displayEdges.map((edge, i) => {
              const s = getPos(edge.source)
              const t = getPos(edge.target)
              if (!s || !t) return null
              const dx = t.x - s.x, dy = t.y - s.y
              const len = Math.sqrt(dx * dx + dy * dy) || 1
              const padS = (getR(edge.source) + 2) * invS
              const padT = (getR(edge.target) + 2) * invS
              const x1 = s.x + dx / len * padS, y1 = s.y + dy / len * padS
              const x2 = t.x - dx / len * padT, y2 = t.y - dy / len * padT
              const isConn = selected && (edge.source === selected || edge.target === selected)
              const dim = selected && !isConn
              const sw = invS
              return (
                <g key={i} style={{ opacity: dim ? 0.08 : isConn ? 1 : 0.6 }} pointerEvents="none">
                  <line x1={x1} y1={y1} x2={x2} y2={y2}
                    stroke={isConn ? '#5302e0' : '#c0b3d8'} strokeWidth={isConn ? sw * 1.5 : sw} />
                  {isConn && edge.label && (
                    <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 4 * invS}
                      textAnchor="middle" fontSize={7 * invS} fill="#9880c0">{edge.label}</text>
                  )}
                </g>
              )
            })}

            {displayNodes.map(node => {
              const p = getPos(node.id)
              if (!p) return null
              const cfg = TYPE_CFG[node.type] || DEFAULT_CFG
              const isSel = selected === node.id
              const isCenter = entityMode && (node.name || '').toLowerCase().includes(centerEntity.toLowerCase())
              const isConn = connectedIds?.has(node.id)
              const dim = selected && !isSel && !isConn
              const r = getR(node.id)
              const label = (node.name || '').length > 22 ? node.name.slice(0, 21) + '…' : node.name
              return (
                <g key={node.id}
                  transform={`translate(${p.x},${p.y}) scale(${invS})`}
                  style={{ opacity: dim ? 0.15 : 1, cursor: 'pointer' }}
                  onMouseDown={e => onNodeDown(e, node.id)}
                  onMouseEnter={() => setHovered(node.id)}
                  onMouseLeave={() => setHovered(null)}>
                  {isSel && <circle r={r + 4} fill="none" stroke="#5302e0" strokeWidth="1.5" />}
                  {isCenter && !isSel && <circle r={r + 6} fill="none" stroke="#f59e0b" strokeWidth="2" strokeDasharray="4 2" />}
                  <circle r={r} fill={cfg.glow}
                    stroke={hovered === node.id || isSel ? 'white' : 'none'}
                    strokeWidth={hovered === node.id || isSel ? 1.5 : 0} />
                  <text x={r + 6} dominantBaseline="middle" fontSize={isSel ? 12 : 11}
                    fontWeight={isSel ? 700 : 500} fill={isSel ? '#5302e0' : '#3a2a5c'}
                    style={{ pointerEvents: 'none' }}>{label}</text>
                </g>
              )
            })}
          </g>
        </svg>
          </>
        )}
      </div>

      {viewMode === 'canvas' && (
      <div className={clsx('shrink-0 transition-all duration-300 overflow-hidden', selected ? 'w-72' : 'w-0')}>
        {selNode && (
          <div className="card h-full overflow-auto" style={{ width: '288px' }}>
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
              <div>
                <div className="label mb-2">Связи ({connectedEdges.length})</div>
                <div className="space-y-1.5">
                  {connectedEdges.map((edge, i) => {
                    const otherId = edge.source === selected ? edge.target : edge.source
                    const other = nodeById[otherId]
                    return (
                      <button key={i} type="button" onClick={() => setSelected(otherId)}
                        className="w-full flex items-center gap-2 p-2 rounded-lg text-xs border bg-surface-900 border-surface-700 text-left hover:border-brand-300">
                        <ChevronRight size={10} className="text-brand-600 shrink-0" />
                        <span className="text-surface-400 shrink-0 text-[10px]">{edge.label}</span>
                        <span className="text-surface-200 truncate">{other?.name}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
      )}
    </div>
  )
}
