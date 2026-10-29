import type { FieldConfidence } from '../types'

const styles: Record<FieldConfidence, string> = {
  high: 'bg-green-100 text-green-800 border-green-300',
  medium: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  low: 'bg-orange-100 text-orange-800 border-orange-300',
  missing: 'bg-red-100 text-red-800 border-red-300',
}

const labels: Record<FieldConfidence, string> = {
  high: 'Confident',
  medium: 'Uncertain',
  low: 'Low confidence',
  missing: 'Missing',
}

export default function ConfidenceBadge({ confidence }: { confidence: FieldConfidence }) {
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium border ${styles[confidence]}`}
    >
      {labels[confidence]}
    </span>
  )
}
