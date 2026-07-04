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
  return edge.label || meta[edge.relation]?.label_ru || (edge.relation || '').replace(/_/g, ' ')
}

export function relationDescription(edge, meta = RELATION_META_FALLBACK) {
  return edge.description || meta[edge.relation]?.description || ''
}

export function relationColor(relation) {
  return RELATION_COLORS[relation] || '#a78bfa'
}

export function edgeKey(edge) {
  return edge.id || `${edge.source}:${edge.relation}:${edge.target}`
}

export function truncateLabel(name, max = 32) {
  const s = name || ''
  return s.length > max ? `${s.slice(0, max - 1)}…` : s
}

export function nodeTypeStyle(type) {
  return TYPE_CFG[type] || DEFAULT_TYPE_CFG
}

export function nodeSize(degree = 1) {
  return Math.min(28, 12 + degree * 2.2)
}

/** Опции vis-network — физика Barnes–Hut как в nickel/visualizer.py (PyVis) */
export function buildVisOptions(showEdgeLabels = true) {
  return {
    autoResize: true,
    layout: { improvedLayout: true },
    physics: {
      enabled: true,
      stabilization: { iterations: 120, fit: true },
      barnesHut: {
        gravitationalConstant: -8000,
        centralGravity: 0.25,
        springLength: 160,
        springConstant: 0.045,
        damping: 0.12,
        avoidOverlap: 0.35,
      },
      minVelocity: 0.75,
    },
    interaction: {
      hover: true,
      hoverConnectedEdges: true,
      selectConnectedEdges: false,
      multiselect: false,
      dragNodes: true,
      dragView: true,
      zoomView: true,
      keyboard: { enabled: true, bindToWindow: false },
      navigationButtons: false,
      tooltipDelay: 300,
    },
    nodes: {
      shape: 'dot',
      font: {
        size: 13,
        color: '#3a2a5c',
        face: 'Inter, system-ui, sans-serif',
        strokeWidth: 3,
        strokeColor: '#ffffff',
      },
      borderWidth: 2,
      borderWidthSelected: 3,
      shadow: {
        enabled: true,
        color: 'rgba(83, 2, 224, 0.18)',
        size: 8,
        x: 0,
        y: 2,
      },
    },
    edges: {
      arrows: { to: { enabled: true, scaleFactor: 0.65 } },
      smooth: {
        enabled: true,
        type: 'dynamic',
        roundness: 0.35,
      },
      font: {
        size: 11,
        color: '#4a3d66',
        background: '#ffffff',
        strokeWidth: 4,
        strokeColor: '#ffffff',
        align: 'middle',
        face: 'Inter, system-ui, sans-serif',
        multi: false,
      },
      labelHighlightBold: true,
      chosen: {
        edge: (values) => {
          values.width = 3
          values.shadow = true
          values.shadowColor = 'rgba(83, 2, 224, 0.35)'
        },
      },
    },
    configure: { enabled: false },
  }
}

export function buildVisNodes(apiNodes, degrees) {
  return apiNodes.map((n) => {
    const deg = degrees[n.id] || 1
    const cfg = nodeTypeStyle(n.type)
    const name = n.name || n.id
    return {
      id: n.id,
      label: truncateLabel(name),
      group: n.type || 'Concept',
      value: deg,
      size: nodeSize(deg),
      color: {
        background: cfg.color,
        border: cfg.border,
        highlight: { background: cfg.color, border: '#5302e0' },
        hover: { background: cfg.color, border: '#5302e0' },
      },
      font: { color: '#3a2a5c' },
      _raw: n,
    }
  })
}

export function buildVisEdges(apiEdges, relationMeta, showLabels) {
  return apiEdges.map((edge, i) => {
    const color = relationColor(edge.relation)
    const label = relationLabel(edge, relationMeta)

    return {
      id: edgeKey(edge),
      from: edge.source,
      to: edge.target,
      label: showLabels ? truncateLabel(label, 22) : '',
      color: {
        color: `${color}cc`,
        highlight: color,
        hover: color,
        opacity: 0.85,
      },
      width: 1.5,
      relation: edge.relation,
      smooth: { type: i % 2 === 0 ? 'curvedCW' : 'curvedCCW', roundness: 0.22 },
      _raw: edge,
    }
  })
}
