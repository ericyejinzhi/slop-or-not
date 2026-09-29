import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { ChannelDetail, VideoListItem } from '../api/types'
import { server } from '../test/mocks/server'
import { createWrapper } from '../test/queryClientWrapper'
import { ChannelViewPage } from './ChannelViewPage'

function renderAtChannel(channelId: string) {
  const Wrapper = createWrapper()
  return render(
    <Wrapper>
      <MemoryRouter initialEntries={[`/channels/${channelId}`]}>
        <Routes>
          <Route path="/channels/:channelId" element={<ChannelViewPage />} />
        </Routes>
      </MemoryRouter>
    </Wrapper>,
  )
}

function makeChannel(overrides: Partial<ChannelDetail> = {}): ChannelDetail {
  return {
    id: 'UC_x',
    handle: '@testchannel',
    title: 'Test Channel',
    description: 'A description.',
    subscriber_count: 5000,
    video_count: 42,
    view_count: 100000,
    last_ingested_at: null,
    ...overrides,
  }
}

function makeVideo(overrides: Partial<VideoListItem> = {}): VideoListItem {
  return {
    id: 'video_1',
    title: 'Channel Video',
    channel_id: 'UC_x',
    channel_handle: '@testchannel',
    published_at: '2026-01-01T00:00:00Z',
    view_count: 10,
    thumbnail_url: null,
    score: null,
    predicted_label: null,
    ...overrides,
  }
}

describe('ChannelViewPage', () => {
  it('renders channel stats and its video grid', async () => {
    server.use(
      http.get('/api/channels/UC_x', () => HttpResponse.json(makeChannel())),
      http.get('/api/videos', () =>
        HttpResponse.json({ items: [makeVideo()], total: 1, limit: 20, offset: 0 }),
      ),
    )
    renderAtChannel('UC_x')

    expect(await screen.findByText('Test Channel')).toBeInTheDocument()
    // "@testchannel" appears twice - once as the channel header, once on the video
    // card - so assert on the count rather than a single unique match.
    expect(screen.getAllByText('@testchannel')).toHaveLength(2)
    expect(screen.getByText('A description.')).toBeInTheDocument()
    expect(screen.getByText(/5,000 subscribers/)).toBeInTheDocument()
    expect(screen.getByText('Never fully ingested')).toBeInTheDocument()
    expect(await screen.findByText('Channel Video')).toBeInTheDocument()
  })

  it('shows the last-ingested date when present', async () => {
    server.use(
      http.get('/api/channels/UC_x', () =>
        HttpResponse.json(makeChannel({ last_ingested_at: '2026-02-01T00:00:00Z' })),
      ),
      http.get('/api/videos', () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    )
    renderAtChannel('UC_x')

    expect(await screen.findByText(/Last ingested/)).toBeInTheDocument()
  })

  it('scopes the video list request to this channel', async () => {
    const capturedUrls: string[] = []
    server.use(
      http.get('/api/channels/UC_x', () => HttpResponse.json(makeChannel())),
      http.get('/api/videos', ({ request }) => {
        capturedUrls.push(request.url)
        return HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 })
      }),
    )
    renderAtChannel('UC_x')

    await screen.findByText('Test Channel')
    await waitFor(() => {
      expect(capturedUrls.some((url) => url.includes('channel_id=UC_x'))).toBe(true)
    })
  })

  it('shows an error message when the channel fails to load', async () => {
    server.use(
      http.get('/api/channels/UC_x', () =>
        HttpResponse.json({ detail: 'not found' }, { status: 404 }),
      ),
    )
    renderAtChannel('UC_x')

    expect(await screen.findByText(/failed to load this channel/i)).toBeInTheDocument()
  })
})
