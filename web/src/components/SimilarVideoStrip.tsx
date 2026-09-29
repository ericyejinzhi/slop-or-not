import { Link } from 'react-router-dom'
import type { SimilarVideo } from '../api/types'

interface SimilarVideoStripProps {
  videos: SimilarVideo[]
}

export function SimilarVideoStrip({ videos }: SimilarVideoStripProps) {
  if (videos.length === 0) {
    return <p className="text-sm text-slate-500">No similar videos found.</p>
  }

  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {videos.map((video) => (
        <Link
          key={video.video_id}
          to={`/videos/${encodeURIComponent(video.video_id)}`}
          className="w-40 flex-shrink-0 rounded-lg border border-slate-200 bg-white p-2 shadow-sm transition hover:shadow-md"
        >
          <div className="flex aspect-video items-center justify-center overflow-hidden rounded bg-slate-100">
            {video.thumbnail_url ? (
              <img
                src={video.thumbnail_url}
                alt={video.title ?? video.video_id}
                className="h-full w-full object-cover"
              />
            ) : (
              <span className="text-xs text-slate-400">No thumbnail</span>
            )}
          </div>
          <p className="mt-1 line-clamp-2 text-xs font-medium text-slate-900">
            {video.title ?? video.video_id}
          </p>
          <p className="text-xs text-slate-400">distance {video.distance.toFixed(3)}</p>
        </Link>
      ))}
    </div>
  )
}
