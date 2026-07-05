export const TYPE_CFG = {
  Process:     { color: '#8b5cf6', border: '#6d28d9' },
  Material:    { color: '#10b981', border: '#047857' },
  Equipment:   { color: '#f59e0b', border: '#b45309' },
  Property:    { color: '#0ea5e9', border: '#0369a1' },
  Parameter:   { color: '#06b6d4', border: '#0e7490' },
  Metric:      { color: '#14b8a6', border: '#0f766e' },
  Expert:      { color: '#f472b6', border: '#be185d' },
  Publication: { color: '#fbbf24', border: '#92400e' },
  Facility:    { color: '#818cf8', border: '#3730a3' },
  Concept:     { color: '#a78bfa', border: '#6d28d9' },
  Document:    { color: '#64748b', border: '#334155' },
  Geography:   { color: '#22c55e', border: '#15803d' },
  Regulation:  { color: '#ef4444', border: '#b91c1c' },
  Product:     { color: '#ec4899', border: '#9d174d' },
  Experiment:  { color: '#6366f1', border: '#4338ca' },
}

export const DEFAULT_TYPE_CFG = { color: '#5302e0', border: '#4200b5' }

export const RELATION_COLORS = {
  uses_material: '#10b981',
  operates_at_condition: '#06b6d4',
  produces_output: '#8b5cf6',
  described_in: '#f59e0b',
  validated_by: '#22c55e',
  contradicts: '#ef4444',
  located_in: '#3b82f6',
  has_property: '#0ea5e9',
  part_of: '#6366f1',
  managed_by: '#ec4899',
  related_to: '#94a3b8',
  can_substitute: '#14b8a6',
}

export const RELATION_META_FALLBACK = {
  uses_material: { label_ru: 'использует материал', description: 'Процесс или установка применяет материал' },
  operates_at_condition: { label_ru: 'работает при условии', description: 'Режим эксплуатации: T, P, расход' },
  produces_output: { label_ru: 'даёт продукт', description: 'Выходной продукт или поток процесса' },
  described_in: { label_ru: 'описано в', description: 'Упоминание в публикации или отчёте' },
  validated_by: { label_ru: 'подтверждено', description: 'Подтверждение экспертом или экспериментом' },
  contradicts: { label_ru: 'противоречит', description: 'Конфликтующие выводы' },
  located_in: { label_ru: 'расположено в', description: 'География или площадка' },
  has_property: { label_ru: 'имеет свойство', description: 'Параметр или характеристика' },
  part_of: { label_ru: 'часть', description: 'Компонент системы' },
  managed_by: { label_ru: 'управляется', description: 'Эксперт или подразделение' },
  related_to: { label_ru: 'связано с', description: 'Ассоциативная связь' },
  can_substitute: { label_ru: 'может заменить', description: 'Альтернатива или заменитель' },
}

export function relationLabel(edge, meta = RELATION_META_FALLBACK) {
  const rel = edgeRelation(edge)
  return edge.label || meta[rel]?.label_ru || rel.replace(/_/g, ' ')
}

export function relationDescription(edge, meta = RELATION_META_FALLBACK) {
  const rel = edgeRelation(edge)
  return meta[rel]?.description || ''
}

/** Текст факта из properties (как tooltip в PyVis). */
export function edgeFactText(edge) {
  return (edge.description || '').trim()
}

/** Детали связи для карточки / панели. */
export function edgeDetailItems(edge) {
  const items = []

  const desc = edgeFactText(edge)
  if (desc) items.push({ label: 'Суть', value: desc })

  const origin = (edge.practice_origin || '').trim()
  if (origin) items.push({ label: 'Практика', value: origin })

  if (edge.confidence != null && edge.confidence !== '') {
    const pct = Number(edge.confidence) <= 1
      ? Math.round(Number(edge.confidence) * 100)
      : Math.round(Number(edge.confidence))
    items.push({ label: 'Уверенность', value: `${pct}%` })
  }
  if (edge.geography) items.push({ label: 'География', value: edge.geography })
  if (edge.source_document) items.push({ label: 'Документ', value: edge.source_document })
  if (edge.verification_status) items.push({ label: 'Верификация', value: edge.verification_status })
  if (edge.document_kind) items.push({ label: 'Тип источника', value: edge.document_kind })
  if (edge.doi) items.push({ label: 'DOI', value: edge.doi })
  if (edge.version != null) items.push({ label: 'Версия', value: String(edge.version) })
  return items
}

export function relationColor(relation) {
  return RELATION_COLORS[relation] || '#a78bfa'
}

export function edgeRelation(edge) {
  return edge.relation || edge.label || 'related_to'
}

export function edgeKey(edge, index) {
  if (edge.visId) return edge.visId
  if (edge.id) return String(edge.id)
  if (edge.fact_id) return `fact:${edge.fact_id}`
  const rel = edgeRelation(edge)
  const base = `${edge.source}:${rel}:${edge.target}`
  return index != null ? `${base}#${index}` : base
}

export function truncateLabel(name, max = 32) {
  const s = name || ''
  return s.length > max ? `${s.slice(0, max - 1)}…` : s
}

export function nodeTypeStyle(type) {
  return TYPE_CFG[type] || DEFAULT_TYPE_CFG
}

export function nodeSize(degree = 1, tier = 'small') {
  const cap = tier === 'large' ? 18 : tier === 'medium' ? 22 : 28
  const base = tier === 'large' ? 8 : tier === 'medium' ? 10 : 12
  const step = tier === 'large' ? 1.2 : tier === 'medium' ? 1.6 : 2.2
  return Math.min(cap, base + degree * step)
}

/** small ≤200, medium ≤800, large — полный граф */
export function graphSizeTier(nodeCount, edgeCount = 0) {
  const n = Math.max(nodeCount, edgeCount)
  if (n <= 250) return 'small'
  if (n <= 1000) return 'medium'
  return 'large'
}

/** Стили vis-network groups по типу сущности (как group в PyVis). */
export function buildVisGroups() {
  const groups = {}
  for (const [type, cfg] of Object.entries(TYPE_CFG)) {
    groups[type] = {
      shape: 'dot',
      color: {
        background: cfg.color,
        border: cfg.border,
        highlight: { background: cfg.color, border: '#5302e0' },
        hover: { background: cfg.color, border: '#5302e0' },
      },
      font: { color: '#3a2a5c', size: 13, strokeWidth: 3, strokeColor: '#ffffff' },
    }
  }
  const d = DEFAULT_TYPE_CFG
  groups.Concept = groups.Concept || {
    shape: 'dot',
    color: {
      background: d.color,
      border: d.border,
      highlight: { background: d.color, border: '#5302e0' },
      hover: { background: d.color, border: '#5302e0' },
    },
    font: { color: '#3a2a5c', size: 13, strokeWidth: 3, strokeColor: '#ffffff' },
  }
  return groups
}

/** Стартовые позиции по секторам типа — визуальная группировка до стабилизации. */
export function assignTypeClusterPositions(apiNodes, degrees = {}) {
  const types = [...new Set(apiNodes.map((n) => n.type || 'Concept'))].sort()
  const typeIndex = Object.fromEntries(types.map((t, i) => [t, i]))
  const typeCount = Math.max(types.length, 1)

  return apiNodes.map((n, i) => {
    const t = n.type || 'Concept'
    const baseAngle = (typeIndex[t] / typeCount) * Math.PI * 2
    const jitter = (((i * 137) % 100) / 100) * 0.9 - 0.45
    const angle = baseAngle + jitter
    const ring = 160 + Math.min((degrees[n.id] || 1) * 14, 120)
    return {
      x: Math.cos(angle) * ring,
      y: Math.sin(angle) * ring,
    }
  })
}

export function buildVisOptions(tier = 'small', { physicsEnabled = true } = {}) {
  const iterations = tier === 'large' ? 35 : tier === 'medium' ? 60 : 100
  const edgeSmooth = tier === 'large'
    ? { enabled: true, type: 'continuous', roundness: 0.08 }
    : { enabled: true, type: 'dynamic', roundness: tier === 'medium' ? 0.22 : 0.32 }

  return {
    autoResize: true,
    groups: buildVisGroups(),
    layout: { improvedLayout: tier !== 'large', clusterThreshold: 150 },
    physics: {
      enabled: true,
      stabilization: {
        iterations,
        fit: true,
        updateInterval: tier === 'large' ? 50 : 25,
      },
      barnesHut: {
        gravitationalConstant: tier === 'large' ? -4200 : -7500,
        centralGravity: tier === 'large' ? 0.14 : 0.22,
        springLength: tier === 'large' ? 120 : 155,
        springConstant: tier === 'large' ? 0.055 : 0.042,
        damping: tier === 'large' ? 0.2 : 0.1,
        avoidOverlap: tier === 'large' ? 0.22 : 0.32,
      },
      minVelocity: tier === 'large' ? 1.4 : 0.6,
      maxVelocity: tier === 'large' ? 24 : 50,
      timestep: tier === 'large' ? 0.65 : 0.5,
    },
    interaction: {
      hover: true,
      hoverConnectedEdges: tier !== 'large',
      selectConnectedEdges: false,
      multiselect: false,
      dragNodes: true,
      dragView: true,
      zoomView: true,
      hideEdgesOnZoom: tier === 'large',
      hideEdgesOnDrag: tier === 'large',
      keyboard: { enabled: false, bindToWindow: false },
      navigationButtons: false,
      tooltipDelay: 300,
    },
    nodes: {
      shape: 'dot',
      font: {
        size: tier === 'large' ? 10 : 13,
        color: '#3a2a5c',
        face: 'Inter, system-ui, sans-serif',
        strokeWidth: tier === 'large' ? 2 : 3,
        strokeColor: '#ffffff',
      },
      borderWidth: 2,
      borderWidthSelected: 3,
      shadow: { enabled: tier === 'small', color: 'rgba(83, 2, 224, 0.15)', size: 6, x: 0, y: 1 },
    },
    edges: {
      arrows: { to: { enabled: tier !== 'large', scaleFactor: 0.5 } },
      smooth: edgeSmooth,
      font: {
        size: tier === 'large' ? 0 : 11,
        color: '#4a3d66',
        background: '#ffffff',
        strokeWidth: 3,
        strokeColor: '#ffffff',
        align: 'middle',
        face: 'Inter, system-ui, sans-serif',
        multi: false,
      },
      labelHighlightBold: true,
      width: tier === 'large' ? 0.7 : 1.4,
      chosen: {
        edge: (values) => {
          values.width = 2.5
          values.shadow = false
        },
      },
    },
    configure: { enabled: false },
  }
}

export function buildVisNodes(apiNodes, degrees, tier = 'small') {
  const labelMinDegree = tier === 'large' ? 4 : tier === 'medium' ? 2 : 0
  const fontSize = tier === 'large' ? 11 : tier === 'medium' ? 12 : 13
  const positions = assignTypeClusterPositions(apiNodes, degrees)

  return apiNodes.map((n, i) => {
    const deg = degrees[n.id] || 1
    const cfg = nodeTypeStyle(n.type)
    const name = n.name || n.id
    const showLabel = deg >= labelMinDegree || tier === 'small'
    return {
      id: n.id,
      label: showLabel ? truncateLabel(name, tier === 'large' ? 20 : 32) : '',
      group: n.type || 'Concept',
      value: deg,
      size: nodeSize(deg, tier),
      x: positions[i].x,
      y: positions[i].y,
      color: {
        background: cfg.color,
        border: cfg.border,
        highlight: { background: cfg.color, border: '#5302e0' },
        hover: { background: cfg.color, border: '#5302e0' },
      },
      font: { color: '#3a2a5c', size: showLabel ? fontSize : 0 },
      _raw: n,
    }
  })
}

export function buildVisEdges(apiEdges, relationMeta, showLabels, tier = 'small') {
  const allowLabels = showLabels
  return apiEdges.map((edge, i) => {
    const rel = edgeRelation(edge)
    const normalized = { ...edge, relation: rel }
    const id = edgeKey(normalized, i)
    const color = relationColor(rel)
    const label = relationLabel(normalized, relationMeta)
    const curved = i % 2 === 0

    return {
      id,
      from: edge.source,
      to: edge.target,
      label: allowLabels ? truncateLabel(label, 22) : '',
      color: {
        color: `${color}cc`,
        highlight: color,
        hover: color,
        opacity: tier === 'large' ? 0.7 : 0.85,
      },
      width: tier === 'large' ? 1 : 1.5,
      relation: rel,
      smooth: tier === 'large'
        ? { type: 'continuous', roundness: 0.1 }
        : { type: curved ? 'curvedCW' : 'curvedCCW', roundness: 0.22 },
      _raw: { ...normalized, visId: id },
    }
  })
}
