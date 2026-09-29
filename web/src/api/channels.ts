import { get } from './client'
import type { ChannelDetail } from './types'

export function getChannel(channelId: string): Promise<ChannelDetail> {
  return get<ChannelDetail>(`/channels/${encodeURIComponent(channelId)}`)
}
