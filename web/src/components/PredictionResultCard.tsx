import { Link } from 'react-router-dom'
import type { PredictResponse, PredictionFactor } from '../api/types'

function formatValue(value: PredictionFactor['value']): string {
  if (value === null) return 'not available'
  if (typeof value === 'string') return value
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2)
}

function FactorRow({ factor, scale }: { factor: PredictionFactor; scale: number }) {
  const towardSlop = factor.contribution > 0
  const width = scale > 0 ? Math.max(4, (Math.abs(factor.contribution) / scale) * 100) : 4
  return (
    <li className="flex items-center gap-3 text-sm">
      <div className="w-56 shrink-0">
        <p className="font-medium text-slate-900">{factor.label}</p>
        <p className="text-xs text-slate-500">{formatValue(factor.value)}</p>
      </div>
      <div className="flex-1">
        <div className="h-2 rounded bg-slate-100">
          <div
            className={`h-2 rounded ${towardSlop ? 'bg-red-400' : 'bg-green-400'}`}
            style={{ width: `${width}%` }}
          />
        </div>
      </div>
      <span
        className={`w-28 shrink-0 text-right text-xs ${towardSlop ? 'text-red-700' : 'text-green-700'}`}
      >
        {towardSlop ? 'points toward slop' : 'points away from slop'}
      </span>
    </li>
  )
}

function ChannelNote({ channel }: { channel: PredictResponse['channel'] }) {
  const name = channel.title ?? 'This channel'
  if (channel.in_dataset && channel.channel_score !== null) {
    return (
      <p className="text-sm text-slate-700">
        {name} is in the dataset. Its average slop score across {channel.scored_video_count}{' '}
        scored videos is {Math.round(channel.channel_score * 100)} out of 100, which is a steadier
        signal than any single video.
      </p>
    )
  }
  if (channel.in_dataset) {
    return <p className="text-sm text-slate-700">{name} is in the dataset.</p>
  }
  return (
    <p className="text-sm text-slate-700">
      {name} is not in the dataset, so there is no channel average to compare this video with.
    </p>
  )
}

export function PredictionResultCard({ result }: { result: PredictResponse }) {
  const slop = result.predicted_label === 'down'
  const percent = Math.round(result.score * 100)
  const scale = Math.max(0, ...result.factors.map((f) => Math.abs(f.contribution)))

  return (
    <section
      aria-label="Prediction result"
      className="space-y-5 rounded-lg border border-slate-200 bg-white p-5"
    >
      <div className="flex flex-wrap gap-4">
        {result.thumbnail_url && (
          <img
            src={result.thumbnail_url}
            alt=""
            className="aspect-video w-56 rounded object-cover"
          />
        )}
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold text-slate-900">{result.title}</h2>
          <p
            className={`mt-2 text-2xl font-bold ${slop ? 'text-red-700' : 'text-green-700'}`}
            data-testid="verdict"
          >
            {slop ? 'Looks like slop' : "Doesn't look like slop"}
          </p>
          <p className="text-sm text-slate-600">Slop score: {percent} out of 100</p>
          <div
            className="mt-2 h-3 w-full max-w-sm rounded bg-slate-100"
            role="meter"
            aria-label="Slop score"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          >
            <div
              className={`h-3 rounded ${slop ? 'bg-red-500' : 'bg-green-500'}`}
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      </div>

      {result.warnings.length > 0 && (
        <ul className="space-y-1 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          {result.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}

      <p className="rounded bg-slate-50 p-3 text-sm text-slate-600">
        This is a statistical guess, not a judgement. It is made from the title, description,
        statistics, comments and thumbnail, and one video is a weaker signal than a whole channel.
        Treat it as a hint.
      </p>

      <div>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          What drove the score
        </h3>
        <ul className="space-y-3">
          {result.factors.map((factor) => (
            <FactorRow key={factor.feature} factor={factor} scale={scale} />
          ))}
        </ul>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          The channel
        </h3>
        <ChannelNote channel={result.channel} />
      </div>

      {result.similar_videos.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Videos with similar thumbnails in the dataset
          </h3>
          <ul className="space-y-1 text-sm">
            {result.similar_videos.map((video) => (
              <li key={video.video_id} className="flex justify-between gap-3">
                <Link
                  to={`/videos/${encodeURIComponent(video.video_id)}`}
                  className="truncate text-slate-900 underline-offset-2 hover:underline"
                >
                  {video.title || video.video_id}
                </Link>
                <span className="shrink-0 text-xs text-slate-500">
                  {video.score === null ? 'unscored' : `score ${Math.round(video.score * 100)}`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-xs text-slate-400">
        Nothing from this check is saved. Based on {result.comments_used} comments.
      </p>
    </section>
  )
}
