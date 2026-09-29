import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/mocks/server'
import { createWrapper } from '../test/queryClientWrapper'
import { useChannel, useVideoDetail, useVideos } from './hooks'
import type { ChannelDetail, VideoDetail, VideoListResponse } from './types'

const sampleListResponse: VideoListResponse = {
  items: [
    {
      id: 'video_1',
      title: 'A Video',
      channel_id: 'UC_x',
      channel_handle: '@channel',
      published_at: '2026-01-01T00:00:00Z',
      view_count: 100,
      thumbnail_url: null,
      score: 0.5,
      predicted_label: 'up',
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
}

describe('useVideos', () => {
  it('fetches and returns the video list', async () => {
    server.use(http.get('/api/videos', () => HttpResponse.json(sampleListResponse)))

    const { result } = renderHook(() => useVideos({}), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(sampleListResponse)
  })

  it('includes query params from the params object', async () => {
    let capturedUrl: string | undefined
    server.use(
      http.get('/api/videos', ({ request }) => {
        capturedUrl = request.url
        return HttpResponse.json(sampleListResponse)
      }),
    )

    const { result } = renderHook(
      () => useVideos({ channel_id: 'UC_x', limit: 5 }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(capturedUrl).toContain('channel_id=UC_x')
    expect(capturedUrl).toContain('limit=5')
  })
})

describe('useVideoDetail', () => {
  it('does not fetch when videoId is undefined', () => {
    const { result } = renderHook(() => useVideoDetail(undefined), {
      wrapper: createWrapper(),
    })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('fetches the video detail when videoId is provided', async () => {
    const detail: VideoDetail = {
      id: 'video_1',
      title: 'A Video',
      description: null,
      channel_id: 'UC_x',
      channel_handle: '@channel',
      published_at: '2026-01-01T00:00:00Z',
      duration_seconds: 120,
      view_count: 100,
      like_count: 10,
      comment_count: 2,
      tags: [],
      thumbnail_url: null,
      score: 0.5,
      predicted_label: 'up',
      model_name: null,
      model_version: null,
      nlp_features: null,
      vision_features: null,
      similar_videos: [],
    }
    server.use(http.get('/api/videos/video_1', () => HttpResponse.json(detail)))

    const { result } = renderHook(() => useVideoDetail('video_1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(detail)
  })
})

describe('useChannel', () => {
  it('fetches channel details', async () => {
    const channel: ChannelDetail = {
      id: 'UC_x',
      handle: '@channel',
      title: 'A Channel',
      description: null,
      subscriber_count: 1000,
      video_count: 10,
      view_count: 50000,
      last_ingested_at: null,
    }
    server.use(http.get('/api/channels/UC_x', () => HttpResponse.json(channel)))

    const { result } = renderHook(() => useChannel('UC_x'), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(channel)
  })
})
