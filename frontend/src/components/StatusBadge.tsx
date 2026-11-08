import type { ClaimStatusType } from '../types'

const styles: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  evidence_pending: 'bg-amber-100 text-amber-800',
  evidence_screened: 'bg-indigo-100 text-indigo-800',
  pending_info: 'bg-yellow-100 text-yellow-800',
  confirmed: 'bg-emerald-100 text-emerald-800',
  dossier_generated: 'bg-purple-100 text-purple-800',
  submitted: 'bg-blue-100 text-blue-800',
  archived: 'bg-slate-100 text-slate-700',
}

const labels: Record<string, string> = {
  draft: 'Draft',
  evidence_pending: 'Evidence Pending',
  evidence_screened: 'Evidence Screened',
  pending_info: 'Pending Info',
  confirmed: 'Customer Confirmed',
  dossier_generated: 'Dossier Ready',
  submitted: 'Submitted (Mock Gateway)',
  archived: 'Archived Vault',
}

export default function StatusBadge({ status }: { status: ClaimStatusType }) {
  const style = styles[status] || styles.draft
  const label = labels[status] || status
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${style}`}>
      {label}
    </span>
  )
}
