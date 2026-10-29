import type { ClaimStatusType } from '../types'

const styles: Record<ClaimStatusType, string> = {
  draft: 'bg-gray-100 text-gray-700',
  pending_info: 'bg-yellow-100 text-yellow-800',
  confirmed: 'bg-green-100 text-green-800',
  submitted: 'bg-blue-100 text-blue-800',
}

const labels: Record<ClaimStatusType, string> = {
  draft: 'Draft',
  pending_info: 'Pending Info',
  confirmed: 'Confirmed',
  submitted: 'Submitted',
}

export default function StatusBadge({ status }: { status: ClaimStatusType }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${styles[status]}`}>
      {labels[status]}
    </span>
  )
}
