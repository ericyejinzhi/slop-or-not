interface LabelBadgeProps {
  label: string
}

const STYLES: Record<string, string> = {
  up: 'bg-green-100 text-green-700',
  down: 'bg-red-100 text-red-700',
  skip: 'bg-slate-200 text-slate-600',
}

export function LabelBadge({ label }: LabelBadgeProps) {
  const colorClass = STYLES[label] ?? STYLES.skip
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colorClass}`}>{label}</span>
  )
}
