import {
  edgeDetailItems,
  edgeFactText,
  edgeRelation,
  relationColor,
  relationDescription,
  relationLabel,
} from './constants'

export function EdgeFactCard({ edge, relationMeta, nodeById, compact = false }) {
  if (!edge) return null

  const rel = edgeRelation(edge)
  const typeDesc = relationDescription(edge, relationMeta)
  const details = edgeDetailItems(edge)
  const hasFact = Boolean(edgeFactText(edge) || details.length > 0)

  const from = edge.source_name || nodeById?.[edge.source]?.name || '?'
  const to = edge.target_name || nodeById?.[edge.target]?.name || '?'

  return (
    <div className={compact ? 'space-y-1' : 'space-y-2'}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span
          className="badge border text-[10px] shrink-0"
          style={{
            color: relationColor(rel),
            borderColor: relationColor(rel),
            background: `${relationColor(rel)}12`,
          }}
        >
          {relationLabel(edge, relationMeta)}
        </span>
        <span className="text-surface-300 font-medium text-xs">
          {from}
          <span className="text-surface-400 mx-1">→</span>
          {to}
        </span>
      </div>

      {typeDesc && !hasFact && (
        <p className="text-[11px] text-surface-400 leading-snug">{typeDesc}</p>
      )}

      {details.map(({ label, value }) => (
        <div key={label} className="text-[11px] leading-snug">
          <span className="text-surface-500">{label}: </span>
          <span className="text-surface-200">{value}</span>
        </div>
      ))}

      {typeDesc && hasFact && (
        <p className="text-[10px] text-surface-500 italic leading-snug border-t border-surface-800 pt-1 mt-1">
          {typeDesc}
        </p>
      )}
    </div>
  )
}
