interface FeatureListItem {
  label: string
  value: string
}

interface FeatureListProps {
  items: FeatureListItem[]
}

export function FeatureList({ items }: FeatureListProps) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
      {items.map((item) => (
        <div key={item.label} className="contents">
          <dt className="text-slate-500">{item.label}</dt>
          <dd className="text-slate-900">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}
