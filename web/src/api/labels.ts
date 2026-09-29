import { buildQuery, get, post } from './client'
import type { LabelCreateRequest, LabelPoolResponse, LabelResponse } from './types'

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
