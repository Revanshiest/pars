import clsx from 'clsx'

const TIER_STYLE = {
  high: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  medium: 'bg-blue-50 text-blue-700 border-blue-200',
  medium_unverified: 'bg-amber-50 text-amber-700 border-amber-200',
  low: 'bg-orange-50 text-orange-700 border-orange-200',
  uncertain: 'bg-surface-800 text-surface-400 border-surface-700',
}

const SOURCE_KIND_LABEL = {
  internal_report: 'Внутренний отчёт',
  publication: 'Публикация',
  regulation: 'Норматив',
  patent: 'Патент',
  report: 'Отчёт',
  experiment_catalog: 'Каталог опытов',
}

export function CredibilityBadge({ credibility, compact }) {
  if (!credibility?.label && !credibility?.tier) return null
  const tier = credibility.tier || 'uncertain'
  return (
    <span className={clsx(
      'badge border text-[10px]',
      TIER_STYLE[tier] || TIER_STYLE.uncertain,
      compact && 'px-1 py-0',
    )}>
      {credibility.label || tier}
    </span>
  )
}

export function SourceMetaBadges({ item }) {
  const cred = item.credibility
  const meta = item.metadata || {}
  const prov = item.provenance || {}
  const kind = prov.document_kind || meta.document_kind
  const kindLabel = SOURCE_KIND_LABEL[kind] || (kind ? kind : null)

  return (
    <div className="flex flex-wrap gap-1 mt-2">
      <CredibilityBadge credibility={cred} compact />
      {kindLabel && (
        <span className="badge bg-surface-900 text-surface-300 border border-surface-700 text-[10px]">
          {kindLabel}
        </span>
      )}
      {(meta.geography || prov.geography) && (
        <span className="badge bg-surface-900 text-surface-300 border border-surface-700 text-[10px]">
          {meta.geography || prov.geography}
        </span>
      )}
      {meta.verification_status === 'verified' && (
        <span className="badge bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px]">
          verified
        </span>
      )}
      {(prov.doi || meta.doi) && (
        <span className="badge bg-surface-900 text-surface-400 border border-surface-700 text-[10px] truncate max-w-[140px]">
          DOI: {prov.doi || meta.doi}
        </span>
      )}
      {(prov.year || meta.year) && (
        <span className="badge bg-surface-900 text-surface-400 border border-surface-700 text-[10px]">
          {prov.year || meta.year}
        </span>
      )}
    </div>
  )
}
