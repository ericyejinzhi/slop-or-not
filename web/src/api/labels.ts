import { buildQuery, get, post } from './client'
import type {
  BatchLabelCreateRequest,
  BatchLabelResponse,
  ChannelBatchPoolResponse,
  LabeledVideoListResponse,
  LabelCreateRequest,
  LabelPoolResponse,
  LabelResponse,
  LabelValue,
} from './types'

export interface LabelPoolParams {
  mode?: 'pool' | 'consistency'
  per_channel_max?: number
  pool_size?: number
  seed?: number
  consistency_sample_size?: number
}

export function getLabelPool(params: LabelPoolParams = {}): Promise<LabelPoolResponse> {
  return get<LabelPoolResponse>(`/labels/pool${buildQuery(params)}`)
}

export function createLabel(body: LabelCreateRequest): Promise<LabelResponse> {
  return post<LabelResponse>('/labels', body)
}

export interface ChannelBatchPoolParams {
  pool_size?: number
  seed?: number
}

export function getChannelBatchPool(
  params: ChannelBatchPoolParams = {},
): Promise<ChannelBatchPoolResponse> {
  return get<ChannelBatchPoolResponse>(`/labels/channel-pool${buildQuery(params)}`)
}

export function createBatchLabel(body: BatchLabelCreateRequest): Promise<BatchLabelResponse> {
  return post<BatchLabelResponse>('/labels/batch', body)
}

export interface ListLabeledVideosParams {
  q?: string
  label?: LabelValue
  limit?: number
  offset?: number
}

export function listLabeledVideos(
  params: ListLabeledVideosParams = {},
): Promise<LabeledVideoListResponse> {
  return get<LabeledVideoListResponse>(`/labels${buildQuery(params)}`)
}
