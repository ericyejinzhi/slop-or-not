// Hand-written mirrors of src/sloppy/api/schemas.py (Python). Kept in sync by hand, not
// generated - see docs/writeups/phase-6/stage-4-api-client.md for the tradeoff this
// implies. Field names and optionality match the Pydantic models exactly; FastAPI
// serializes datetime fields as ISO 8601 strings, so those are typed `string` here, not
// `Date` - parse with `new Date(...)` at render time where needed.

export interface NlpFeatureBreakdown {
  comment_count_scored: number
  sentiment_mean: number | null
  sentiment_std: number | null
  sentiment_negative_share: number | null
  slop_keyword_rate: number | null
  topic_cluster_count: number | null
  topic_top_cluster_share: number | null
  topic_top_cluster_sentiment: number | null
  topic_sentiment_spread: number | null
  title_lure_score: number | null
  title_mysterious_score: number | null
  title_transparent_score: number | null
}

export interface VisionFeatureBreakdown {
  clip_clickbait_score: number | null
  clip_ai_generated_score: number | null
  clip_text_heavy_score: number | null
}

export interface SimilarVideo {
  video_id: string
  distance: number
  title: string | null
  thumbnail_url: string | null
}

export interface VideoListItem {
  id: string
  title: string
  channel_id: string
  channel_handle: string | null
  published_at: string
  view_count: number | null
  thumbnail_url: string | null
  score: number | null
  predicted_label: string | null
}

export interface VideoListResponse {
  items: VideoListItem[]
  total: number
  limit: number
  offset: number
}

export interface VideoDetail {
  id: string
  title: string
  description: string | null
  channel_id: string
  channel_handle: string | null
  published_at: string
  duration_seconds: number | null
  view_count: number | null
  like_count: number | null
  comment_count: number | null
  tags: string[]
  thumbnail_url: string | null
  score: number | null
  predicted_label: string | null
  model_name: string | null
  model_version: string | null
  nlp_features: NlpFeatureBreakdown | null
  vision_features: VisionFeatureBreakdown | null
  similar_videos: SimilarVideo[]
}

export interface ChannelDetail {
  id: string
  handle: string | null
  title: string
  description: string | null
  subscriber_count: number | null
  video_count: number | null
  view_count: number | null
  last_ingested_at: string | null
}

export interface LabelPoolItem {
  video_id: string
  title: string
  channel_id: string
  channel_handle: string | null
  published_at: string
  duration_seconds: number | null
  view_count: number | null
  like_count: number | null
  comment_count: number | null
  thumbnail_url: string | null
}

export interface LabelPoolResponse {
  items: LabelPoolItem[]
}

export type LabelValue = 'up' | 'down' | 'skip'

export interface LabelCreateRequest {
  video_id: string
  labeler?: string | null
  label: LabelValue
  notes?: string | null
}

export interface LabelResponse {
  video_id: string
  labeler: string
  label: string
  notes: string | null
  created_at: string
}

export interface IngestRequest {
  channel?: string | null
  video_id?: string | null
}

export interface IngestResponse {
  status: 'accepted'
  target: string
}
