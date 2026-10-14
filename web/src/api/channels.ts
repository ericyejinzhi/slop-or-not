import { get } from './client'
import type { ChannelDetail, ChannelListResponse } from './types'

export interface ListChannelsParams {
  limit?: number
  offset?: number
  sort?: 'score' | 'title' | 'subscriber_count' | 'ingested_video_count'
  order?: 'asc' | 'desc'
  predicted_label?: 'up' | 'down'
}

export function getChannel(channelId: string): Promise<ChannelDetail> {
  return get<ChannelDetail>(`/channels/${encodeURIComponent(channelId)}`)
}

export function listChannels(params: ListChannelsParams = {}): Promise<ChannelListResponse> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value))
  }
  const suffix = query.toString()
  return get<ChannelListResponse>(suffix ? `/channels?${suffix}` : '/channels')
}
