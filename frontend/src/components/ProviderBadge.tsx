interface ProviderBadgeProps {
  isMock: boolean
  model?: string
  className?: string
}

export default function ProviderBadge({ isMock, model, className = '' }: ProviderBadgeProps) {
  if (isMock) {
    return (
      <span
        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300 ${className}`}
        title="Simulated output - No external API called"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
        DEMO / SIMULATED
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-300 ${className}`}
      title={`Live output from ${model || 'Gnani Speech API'}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
      GNANI AI [LIVE] {model ? `(${model})` : ''}
    </span>
  )
}

