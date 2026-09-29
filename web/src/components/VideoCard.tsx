import { Link } from 'react-router-dom'
import type { VideoListItem } from '../api/types'
import { ScoreBadge } from './ScoreBadge'

interface VideoCardProps {
  video: VideoListItem
}

export function VideoCard({ video }: VideoCardProps) {
  return (
    <Link
      to={`/videos/${encodeURIComponent(video.id)}`}
      className="block overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm transition hover:shadow-md"
    >
      <div className="flex aspect-video items-center justify-center bg-slate-100">
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
      <div className="space-y-1 p-3">
        <h3 className="line-clamp-2 text-sm font-medium text-slate-900">{video.title}</h3>
        <p className="text-xs text-slate-500">{video.channel_handle ?? video.channel_id}</p>
        <div className="flex items-center justify-between pt-1">
          <ScoreBadge score={video.score} predictedLabel={video.predicted_label} />
          {video.view_count !== null && (
            <span className="text-xs text-slate-400">
              {video.view_count.toLocaleString()} views
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}
