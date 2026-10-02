import { useEffect, useRef, useState } from 'react'
import {
  useChannelBatchPool,
  useCreateBatchLabel,
  useCreateLabel,
  useLabelPool,
} from '../api/hooks'
import type { LabelPoolItem, LabelValue } from '../api/types'
import { formatCount, formatDate } from '../lib/format'
import { readStoredLabeler, writeStoredLabeler } from '../lib/labeler'

type Mode = 'channel' | 'video'

function modeToggleClass(active: boolean): string {
  return `rounded px-2 py-1 text-sm font-medium ${
    active ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
  }`
}

export function LabelingPage() {
  const [labeler, setLabeler] = useState(readStoredLabeler)
  // Channel-batch is the default - the project's current primary labeling methodology
  // (see docs/writeups/TODO.md). Per-video stays available for manual override, though
  // the main override path day-to-day is the /labeled page's inline relabel buttons.
  const [mode, setMode] = useState<Mode>('channel')
  const [sessionCount, setSessionCount] = useState(0)

  function persistLabeler(value: string) {
    setLabeler(value)
    writeStoredLabeler(value)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
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
        <div className="flex gap-1 rounded border border-slate-300 p-0.5">
          <button
            type="button"
            onClick={() => setMode('channel')}
            className={modeToggleClass(mode === 'channel')}
          >
            By channel
          </button>
          <button
            type="button"
            onClick={() => setMode('video')}
            className={modeToggleClass(mode === 'video')}
          >
            By video
          </button>
        </div>
        <span className="text-sm text-slate-500">Labeled {sessionCount} this session</span>
      </div>

      {mode === 'channel' ? (
        <ChannelModeView labeler={labeler} onLabeled={(n) => setSessionCount((c) => c + n)} />
      ) : (
        <VideoModeView labeler={labeler} onLabeled={(n) => setSessionCount((c) => c + n)} />
      )}
    </div>
  )
}

function VideoCardThumbnail({ video }: { video: LabelPoolItem }) {
  return (
    <div className="flex aspect-video items-center justify-center overflow-hidden rounded bg-slate-100">
      {video.thumbnail_url ? (
        <img
          src={video.thumbnail_url}
          alt={video.title}
          className="h-full w-full object-cover"
        />
      ) : (
        <span className="text-xs text-slate-400">No thumbnail</span>
      )}
    </div>
  )
}

function YouTubeLink({ videoId, className }: { videoId: string; className: string }) {
  return (
    <a
      href={`https://www.youtube.com/watch?v=${videoId}`}
      target="_blank"
      rel="noreferrer"
      className={className}
    >
      Open on YouTube ↗
    </a>
  )
}

function VideoModeView({
  labeler,
  onLabeled,
}: {
  labeler: string
  onLabeled: (count: number) => void
}) {
  const [index, setIndex] = useState(0)
  // Set once a refetch (triggered when the pool runs out) comes back with zero items -
  // the real signal that there's genuinely nothing left to label, vs. mid-refill.
  const [exhausted, setExhausted] = useState(false)
  // Re-entrancy guard only - never rendered, so a ref (not state) avoids an extra render.
  const isRefillingRef = useRef(false)

  const { data, isLoading, isError, refetch } = useLabelPool({})
  const createLabel = useCreateLabel()

  const items = data?.items ?? []
  const current = items[index]

  // When the session runs off the end of the fetched pool, fetch a fresh one instead of
  // dead-ending - the backend's own exclude_labeled already keeps it from handing back
  // videos labeled (or skipped) this session, so this just keeps the session going until
  // a refetch genuinely comes back empty.
  useEffect(() => {
    if (isLoading || isRefillingRef.current || exhausted) return
    if (items.length === 0 || index < items.length) return

    isRefillingRef.current = true
    void refetch()
      .then((result) => {
        if ((result.data?.items.length ?? 0) === 0) {
          setExhausted(true)
        } else {
          setIndex(0)
        }
      })
      .finally(() => {
        isRefillingRef.current = false
      })
  }, [index, items.length, isLoading, exhausted, refetch])

  function handleLabel(label: LabelValue) {
    if (!current || createLabel.isPending) return
    createLabel.mutate(
      { video_id: current.video_id, label, labeler: labeler || undefined },
      {
        onSuccess: () => {
          onLabeled(1)
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

  if (!current) {
    return (
      <p className="text-slate-600">
        {items.length > 0
          ? 'Loading more videos...'
          : exhausted
            ? 'No more videos available to label right now - nice work.'
            : 'No videos available to label.'}
      </p>
    )
  }

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
      <VideoCardThumbnail video={current} />
      <div>
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-lg font-medium text-slate-900">{current.title}</h2>
          <YouTubeLink
            videoId={current.video_id}
            className="shrink-0 text-sm text-blue-600 hover:underline"
          />
        </div>
        <p className="text-sm text-slate-500">
          {current.channel_handle ?? current.channel_id} {'·'} {formatDate(current.published_at)}
        </p>
        <p className="text-sm text-slate-600">
          {formatCount(current.view_count)} views {'·'} {formatCount(current.like_count)} likes{' '}
          {'·'} {formatCount(current.comment_count)} comments
        </p>
      </div>
      <LabelButtons onLabel={handleLabel} disabled={createLabel.isPending} />
      {createLabel.isError && (
        <p className="text-sm text-red-600">Failed to save that label - try again.</p>
      )}
    </div>
  )
}

function ChannelModeView({
  labeler,
  onLabeled,
}: {
  labeler: string
  onLabeled: (count: number) => void
}) {
  const [index, setIndex] = useState(0)
  const [exhausted, setExhausted] = useState(false)
  const isRefillingRef = useRef(false)

  const { data, isLoading, isError, refetch } = useChannelBatchPool({})
  const createBatchLabel = useCreateBatchLabel()

  const batches = data?.items ?? []
  const current = batches[index]

  // Same auto-refill shape as VideoModeView - see its comment for the rationale.
  useEffect(() => {
    if (isLoading || isRefillingRef.current || exhausted) return
    if (batches.length === 0 || index < batches.length) return

    isRefillingRef.current = true
    void refetch()
      .then((result) => {
        if ((result.data?.items.length ?? 0) === 0) {
          setExhausted(true)
        } else {
          setIndex(0)
        }
      })
      .finally(() => {
        isRefillingRef.current = false
      })
  }, [index, batches.length, isLoading, exhausted, refetch])

  function handleLabel(label: LabelValue) {
    if (!current || createBatchLabel.isPending) return
    createBatchLabel.mutate(
      {
        channel_id: current.channel_id,
        video_ids: current.videos.map((video) => video.video_id),
        label,
        labeler: labeler || undefined,
      },
      {
        onSuccess: () => {
          onLabeled(current.videos.length)
          setIndex((i) => i + 1)
        },
      },
    )
  }

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

  if (!current) {
    return (
      <p className="text-slate-600">
        {batches.length > 0
          ? 'Loading more channels...'
          : exhausted
            ? 'No more channels available to label right now - nice work.'
            : 'No channels available to label.'}
      </p>
    )
  }

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="text-lg font-medium text-slate-900">
        {current.channel_handle ?? current.channel_id}
      </h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
        {current.videos.map((video) => (
          <div key={video.video_id} className="space-y-1">
            <VideoCardThumbnail video={video} />
            <p className="truncate text-xs font-medium text-slate-900">{video.title}</p>
            <p className="text-xs text-slate-500">{formatCount(video.view_count)} views</p>
            <YouTubeLink videoId={video.video_id} className="text-xs text-blue-600 hover:underline" />
          </div>
        ))}
      </div>
      <LabelButtons onLabel={handleLabel} disabled={createBatchLabel.isPending} />
      {createBatchLabel.isError && (
        <p className="text-sm text-red-600">Failed to save that label - try again.</p>
      )}
    </div>
  )
}

function LabelButtons({
  onLabel,
  disabled,
}: {
  onLabel: (label: LabelValue) => void
  disabled: boolean
}) {
  return (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={() => onLabel('up')}
        disabled={disabled}
        className="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
      >
        (y) Up
      </button>
      <button
        type="button"
        onClick={() => onLabel('down')}
        disabled={disabled}
        className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
      >
        (n) Down
      </button>
      <button
        type="button"
        onClick={() => onLabel('skip')}
        disabled={disabled}
        className="rounded bg-slate-400 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
      >
        (s) Skip
      </button>
    </div>
  )
}
