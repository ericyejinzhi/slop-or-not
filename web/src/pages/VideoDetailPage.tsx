import { Link, useParams } from 'react-router-dom'
import { useVideoDetail } from '../api/hooks'
import { FeatureList } from '../components/FeatureList'
import { ScoreBadge } from '../components/ScoreBadge'
import { SimilarVideoStrip } from '../components/SimilarVideoStrip'
import { formatCount, formatDate, formatNumber } from '../lib/format'

export function VideoDetailPage() {
  const { videoId } = useParams<{ videoId: string }>()
  const { data, isLoading, isError } = useVideoDetail(videoId)

  if (isLoading) {
    return <p className="text-slate-600">Loading video...</p>
  }
  if (isError) {
    return <p className="text-red-600">Failed to load this video.</p>
  }
  if (!data) {
    return null
  }

  const nlpItems = data.nlp_features
    ? [
        { label: 'Sentiment mean', value: formatNumber(data.nlp_features.sentiment_mean) },
        { label: 'Sentiment std', value: formatNumber(data.nlp_features.sentiment_std) },
        {
          label: 'Negative share',
          value: formatNumber(data.nlp_features.sentiment_negative_share),
        },
        { label: 'Slop keyword rate', value: formatNumber(data.nlp_features.slop_keyword_rate) },
        {
          label: 'Topic clusters',
          value: data.nlp_features.topic_cluster_count?.toString() ?? '-',
        },
        {
          label: 'Top cluster share',
          value: formatNumber(data.nlp_features.topic_top_cluster_share),
        },
        { label: 'Lure score', value: formatNumber(data.nlp_features.title_lure_score) },
        {
          label: 'Mysterious score',
          value: formatNumber(data.nlp_features.title_mysterious_score),
        },
        {
          label: 'Transparent score',
          value: formatNumber(data.nlp_features.title_transparent_score),
        },
      ]
    : []

  const visionItems = data.vision_features
    ? [
        {
          label: 'Clickbait score',
          value: formatNumber(data.vision_features.clip_clickbait_score),
        },
        {
          label: 'AI-generated score',
          value: formatNumber(data.vision_features.clip_ai_generated_score),
        },
        {
          label: 'Text-heavy score',
          value: formatNumber(data.vision_features.clip_text_heavy_score),
        },
      ]
    : []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="flex aspect-video w-full flex-shrink-0 items-center justify-center overflow-hidden rounded-lg bg-slate-100 sm:w-80">
          {data.thumbnail_url ? (
            <img
              src={data.thumbnail_url}
              alt={data.title}
              className="h-full w-full object-cover"
            />
          ) : (
            <span className="text-xs text-slate-400">No thumbnail</span>
          )}
        </div>
        <div className="flex-1 space-y-2">
          <h1 className="text-xl font-semibold text-slate-900">{data.title}</h1>
          <p className="text-sm text-slate-500">
            <Link
              to={`/channels/${encodeURIComponent(data.channel_id)}`}
              className="underline"
            >
              {data.channel_handle ?? data.channel_id}
            </Link>
            {' · '}
            {formatDate(data.published_at)}
          </p>
          <ScoreBadge score={data.score} predictedLabel={data.predicted_label} />
          <p className="text-sm text-slate-600">
            {formatCount(data.view_count)} views {'·'} {formatCount(data.like_count)} likes{' '}
            {'·'} {formatCount(data.comment_count)} comments
          </p>
          {data.description && (
            <p className="whitespace-pre-line text-sm text-slate-700">{data.description}</p>
          )}
          {data.tags.length > 0 && (
            <p className="text-xs text-slate-400">{data.tags.join(', ')}</p>
          )}
        </div>
      </div>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-900">NLP features</h2>
        {data.nlp_features ? (
          <FeatureList items={nlpItems} />
        ) : (
          <p className="text-sm text-slate-500">Not computed yet for this video.</p>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-900">Vision features</h2>
        {data.vision_features ? (
          <FeatureList items={visionItems} />
        ) : (
          <p className="text-sm text-slate-500">Not computed yet for this video.</p>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-900">Similar videos</h2>
        <SimilarVideoStrip videos={data.similar_videos} />
      </section>
    </div>
  )
}
