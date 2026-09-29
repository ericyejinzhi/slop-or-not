import type { OrderOption, PredictedLabelFilter, SortOption } from '../hooks/useVideoListState'

interface VideoListControlsProps {
  sort: SortOption
  onSortChange: (value: SortOption) => void
  order: OrderOption
  onOrderChange: (value: OrderOption) => void
  predictedLabel: PredictedLabelFilter
  onPredictedLabelChange: (value: PredictedLabelFilter) => void
}

export function VideoListControls({
  sort,
  onSortChange,
  order,
  onOrderChange,
  predictedLabel,
  onPredictedLabelChange,
}: VideoListControlsProps) {
  return (
    <div className="flex flex-wrap items-center gap-4">
      <label className="text-sm text-slate-600">
        Sort{' '}
        <select
          className="ml-1 rounded border border-slate-300 px-2 py-1 text-sm"
          value={sort}
          onChange={(event) => onSortChange(event.target.value as SortOption)}
        >
          <option value="published_at">Published</option>
          <option value="view_count">Views</option>
          <option value="score">Score</option>
        </select>
      </label>
      <label className="text-sm text-slate-600">
        Order{' '}
        <select
          className="ml-1 rounded border border-slate-300 px-2 py-1 text-sm"
          value={order}
          onChange={(event) => onOrderChange(event.target.value as OrderOption)}
        >
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
      </label>
      <label className="text-sm text-slate-600">
        Filter{' '}
        <select
          className="ml-1 rounded border border-slate-300 px-2 py-1 text-sm"
          value={predictedLabel}
          onChange={(event) =>
            onPredictedLabelChange(event.target.value as PredictedLabelFilter)
          }
        >
          <option value="">All</option>
          <option value="up">Predicted up</option>
          <option value="down">Predicted down</option>
        </select>
      </label>
    </div>
  )
}
