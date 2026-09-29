import { useEffect, useState } from 'react'
import { useCreateLabel, useLabelPool } from '../api/hooks'
import type { LabelValue } from '../api/types'
import { formatCount, formatDate } from '../lib/format'

const LABELER_STORAGE_KEY = 'slop-or-not:labeler'

function readStoredLabeler(): string {
  try {
    return localStorage.getItem(LABELER_STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function LabelingPage() {
  const [labeler, setLabeler] = useState(readStoredLabeler)
  const [index, setIndex] = useState(0)
  const [sessionCount, setSessionCount] = useState(0)

  const { data, isLoading, isError } = useLabelPool({})
  const createLabel = useCreateLabel()

  const items = data?.items ?? []
  const current = items[index]

  function persistLabeler(value: string) {
    setLabeler(value)
    try {
      localStorage.setItem(LABELER_STORAGE_KEY, value)
    } catch {
      // best-effort only - labeling still works without persistence
    }
  }

  function handleLabel(label: LabelValue) {
    if (!current || createLabel.isPending) return
    createLabel.mutate(
      { video_id: current.video_id, label, labeler: labeler || undefined },
      {
        onSuccess: () => {
          setSessionCount((count) => count + 1)
          setIndex((i) => i + 1)
        },
      },
    )
  }

  // Re-registered on every render (no dependency array) so the listener always closes
  // over the current `current`/`labeler`/`createLabel.isPending` values - avoids a stale
  // closure that would keep labeling the first video after the pool advances.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'y') handleLabel('up')
      else if (event.key === 'n') handleLabel('down')
      else if (event.key === 's') handleLabel('skip')
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  })

  if (isLoading) {
    return <p className="text-slate-600">Loading labeling pool...</p>
  }
  if (isError) {
    return <p className="text-red-600">Failed to load the labeling pool.</p>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <label className="text-sm text-slate-600" htmlFor="labeler-name">
          Labeler
        </label>
        <input
          id="labeler-name"
          type="text"
          className="rounded border border-slate-300 px-2 py-1 text-sm"
          value={labeler}
          onChange={(event) => persistLabeler(event.target.value)}
          placeholder="your name"
        />
        <span className="text-sm text-slate-500">Labeled {sessionCount} this session</span>
      </div>

      {!current ? (
        <p className="text-slate-600">
          {items.length === 0
            ? 'No videos available to label.'
            : 'Pool complete for this session.'}
        </p>
      ) : (
        <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex aspect-video items-center justify-center overflow-hidden rounded bg-slate-100">
            {current.thumbnail_url ? (
              <img
                src={current.thumbnail_url}
                alt={current.title}
                className="h-full w-full object-cover"
              />
            ) : (
              <span className="text-xs text-slate-400">No thumbnail</span>
            )}
          </div>
          <div>
            <h2 className="text-lg font-medium text-slate-900">{current.title}</h2>
            <p className="text-sm text-slate-500">
              {current.channel_handle ?? current.channel_id} {'·'}{' '}
              {formatDate(current.published_at)}
            </p>
            <p className="text-sm text-slate-600">
              {formatCount(current.view_count)} views {'·'}{' '}
              {formatCount(current.like_count)} likes {'·'}{' '}
              {formatCount(current.comment_count)} comments
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => handleLabel('up')}
              disabled={createLabel.isPending}
              className="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
            >
              (y) Up
            </button>
            <button
              type="button"
              onClick={() => handleLabel('down')}
              disabled={createLabel.isPending}
              className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
            >
              (n) Down
            </button>
            <button
              type="button"
              onClick={() => handleLabel('skip')}
              disabled={createLabel.isPending}
              className="rounded bg-slate-400 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
            >
              (s) Skip
            </button>
          </div>
          {createLabel.isError && (
            <p className="text-sm text-red-600">Failed to save that label - try again.</p>
          )}
        </div>
      )}
    </div>
  )
}
