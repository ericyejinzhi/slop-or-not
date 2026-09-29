import type { VideoListItem } from '../api/types'
import { VideoCard } from './VideoCard'

interface VideoGridProps {
  items: VideoListItem[]
  total: number
  offset: number
  pageSize: number
  isLoading: boolean
  isError: boolean
  onPrevious: () => void
  onNext: () => void
}

export function VideoGrid({
  items,
  total,
  offset,
  pageSize,
  isLoading,
  isError,
  onPrevious,
  onNext,
}: VideoGridProps) {
  if (isLoading) {
    return <p className="text-slate-600">Loading videos...</p>
  }
  if (isError) {
    return <p className="text-red-600">Failed to load videos.</p>
  }

  return (
    <>
      {items.length === 0 ? (
        <p className="text-slate-600">No videos match these filters.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {items.map((video) => (
            <VideoCard key={video.id} video={video} />
          ))}
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        <button
          type="button"
          className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
          onClick={onPrevious}
          disabled={offset === 0}
        >
          Previous
        </button>
        <span className="text-sm text-slate-500">
          {total === 0 ? '0 videos' : `${offset + 1}-${Math.min(offset + pageSize, total)} of ${total}`}
        </span>
        <button
          type="button"
          className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
          onClick={onNext}
          disabled={offset + pageSize >= total}
        >
          Next
        </button>
      </div>
    </>
  )
}
