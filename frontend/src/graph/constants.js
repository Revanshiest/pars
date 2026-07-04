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

/** Геометрия дуги со стрелкой между двумя узлами */
export function edgeGeometry(s, t, r1, r2, invS, index = 0) {
  const dx = t.x - s.x
  const dy = t.y - s.y
  const len = Math.sqrt(dx * dx + dy * dy) || 1
  const padS = (r1 + 3) * invS
  const padT = (r2 + 8) * invS
  const x1 = s.x + (dx / len) * padS
  const y1 = s.y + (dy / len) * padS
  const x2 = t.x - (dx / len) * padT
  const y2 = t.y - (dy / len) * padT
  const mx = (x1 + x2) / 2
  const my = (y1 + y2) / 2
  const nx = -dy / len
  const ny = dx / len
  const spread = ((index % 3) - 1) * 18
  const curve = Math.min(50, len * 0.12) + spread
  const cx = mx + nx * curve
  const cy = my + ny * curve
  return {
    x1, y1, x2, y2, cx, cy,
    lx: cx,
    ly: cy,
    path: `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`,
  }
}
