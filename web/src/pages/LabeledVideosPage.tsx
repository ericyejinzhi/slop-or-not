import { useEffect, useState } from 'react'
import { useCreateLabel, useLabeledVideos } from '../api/hooks'
import type { LabelValue } from '../api/types'
import { LabelBadge } from '../components/LabelBadge'
import { formatDate } from '../lib/format'
import { readStoredLabeler } from '../lib/labeler'

const PAGE_SIZE = 20
const SEARCH_DEBOUNCE_MS = 300

type LabelFilter = 'all' | LabelValue

export function LabeledVideosPage() {
  const [searchInput, setSearchInput] = useState('')
  const [q, setQ] = useState('')
  const [labelFilter, setLabelFilter] = useState<LabelFilter>('all')
  const [offset, setOffset] = useState(0)

  // Debounced so typing doesn't fire a request per keystroke - committed value resets
  // pagination back to page 1, since the old offset is meaningless against new results.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(searchInput.trim())
      setOffset(0)
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [searchInput])

  const { data, isLoading, isError } = useLabeledVideos({
    q: q || undefined,
    label: labelFilter === 'all' ? undefined : labelFilter,
    limit: PAGE_SIZE,
    offset,
  })
  const relabel = useCreateLabel()
  const [relabelingVideoId, setRelabelingVideoId] = useState<string | null>(null)

  const items = data?.items ?? []
  const total = data?.total ?? 0

  function handleRelabel(videoId: string, label: LabelValue) {
    setRelabelingVideoId(videoId)
    relabel.mutate(
      { video_id: videoId, label, labeler: readStoredLabeler() || undefined },
      { onSettled: () => setRelabelingVideoId(null) },
    )
  }

  function handleLabelFilterChange(value: LabelFilter) {
    setLabelFilter(value)
    setOffset(0)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          className="min-w-48 rounded border border-slate-300 px-2 py-1.5 text-sm"
          placeholder="Search by title..."
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
        />
        <select
          className="rounded border border-slate-300 px-2 py-1.5 text-sm"
          value={labelFilter}
          onChange={(event) => handleLabelFilterChange(event.target.value as LabelFilter)}
        >
          <option value="all">All labels</option>
          <option value="up">Up</option>
          <option value="down">Down</option>
          <option value="skip">Skip</option>
        </select>
      </div>

      {isLoading ? (
        <p className="text-slate-600">Loading labeled videos...</p>
      ) : isError ? (
        <p className="text-red-600">Failed to load labeled videos.</p>
      ) : items.length === 0 ? (
        <p className="text-slate-600">No labeled videos match these filters.</p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.video_id}
              className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-3"
            >
              <div className="h-16 w-28 shrink-0 overflow-hidden rounded bg-slate-100">
                {item.thumbnail_url ? (
                  <img
                    src={item.thumbnail_url}
                    alt={item.title}
                    className="h-full w-full object-cover"
                  />
                ) : null}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="truncate text-sm font-medium text-slate-900">{item.title}</h3>
                  <a
                    href={`https://www.youtube.com/watch?v=${item.video_id}`}
                    target="_blank"
                    rel="noreferrer"
                    className="shrink-0 text-xs text-blue-600 hover:underline"
                  >
                    YouTube ↗
                  </a>
                </div>
                <p className="text-xs text-slate-500">
                  {item.channel_handle ?? item.channel_id} {'·'} labeled{' '}
                  {item.label_count > 1 ? `${item.label_count} times` : 'once'} {'·'} last by{' '}
                  {item.labeler} on {formatDate(item.labeled_at)}
                </p>
              </div>
              <LabelBadge label={item.label} />
              <div className="flex shrink-0 gap-1">
                <button
                  type="button"
                  onClick={() => handleRelabel(item.video_id, 'up')}
                  disabled={relabelingVideoId === item.video_id}
                  className="rounded bg-green-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-40"
                >
                  Up
                </button>
                <button
                  type="button"
                  onClick={() => handleRelabel(item.video_id, 'down')}
                  disabled={relabelingVideoId === item.video_id}
                  className="rounded bg-red-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-40"
                >
                  Down
                </button>
                <button
                  type="button"
                  onClick={() => handleRelabel(item.video_id, 'skip')}
                  disabled={relabelingVideoId === item.video_id}
                  className="rounded bg-slate-400 px-2 py-1 text-xs font-medium text-white disabled:opacity-40"
                >
                  Skip
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        <button
          type="button"
          className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          disabled={offset === 0}
        >
          Previous
        </button>
        <span className="text-sm text-slate-500">
          {total === 0 ? '0 videos' : `${offset + 1}-${Math.min(offset + PAGE_SIZE, total)} of ${total}`}
        </span>
        <button
          type="button"
          className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
          onClick={() => setOffset(offset + PAGE_SIZE)}
          disabled={offset + PAGE_SIZE >= total}
        >
          Next
        </button>
      </div>
    </div>
  )
}
