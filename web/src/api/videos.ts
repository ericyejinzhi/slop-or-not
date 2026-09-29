import { buildQuery, get } from './client'
import type { VideoDetail, VideoListResponse } from './types'

export interface ListVideosParams {
  limit?: number
  offset?: number
  sort?: 'published_at' | 'view_count' | 'score'
  order?: 'asc' | 'desc'
  channel_id?: string
  predicted_label?: 'up' | 'down'
  model_name?: string
  model_version?: string
}

export function listVideos(params: ListVideosParams = {}): Promise<VideoListResponse> {
  return get<VideoListResponse>(`/videos${buildQuery(params)}`)
}

export interface VideoDetailParams {
  model_name?: string
  model_version?: string
}

export function getVideoDetail(
  videoId: string,
  params: VideoDetailParams = {},
): Promise<VideoDetail> {
  return get<VideoDetail>(`/videos/${encodeURIComponent(videoId)}${buildQuery(params)}`)
}
