interface ScoreBadgeProps {
  score: number | null
  predictedLabel: string | null
}

export function ScoreBadge({ score, predictedLabel }: ScoreBadgeProps) {
  if (score === null || predictedLabel === null) {
    return (
      <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-600">
        Unscored
      </span>
    )
  }

  const colorClass =
    predictedLabel === 'down' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'

  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colorClass}`}>
      {predictedLabel} ({score.toFixed(2)})
    </span>
  )
}
