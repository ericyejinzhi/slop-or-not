import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AppRoutes } from './routes'
import { server } from './test/mocks/server'
import { createWrapper } from './test/queryClientWrapper'

const emptyVideoList = { items: [], total: 0, limit: 20, offset: 0 }

function mockEmptyVideoList() {
  server.use(http.get('/api/videos', () => HttpResponse.json(emptyVideoList)))
}

function mockEmptyLabelPool() {
  server.use(http.get('/api/labels/pool', () => HttpResponse.json({ items: [] })))
  server.use(http.get('/api/labels/channel-pool', () => HttpResponse.json({ items: [] })))
}

function renderAt(path: string) {
  const Wrapper = createWrapper()
  return render(
    <Wrapper>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </Wrapper>,
  )
}

describe('AppRoutes', () => {
  it('renders the video grid page at /', async () => {
    mockEmptyVideoList()
    renderAt('/')
    expect(await screen.findByText(/no videos match these filters/i)).toBeInTheDocument()
  })

  it('renders the labeling page at /label', async () => {
    mockEmptyLabelPool()
    renderAt('/label')
    expect(await screen.findByText(/no channels available to label/i)).toBeInTheDocument()
  })

  it('renders the video detail page with the videoId param at /videos/:videoId', async () => {
    server.use(
      http.get('/api/videos/abc123', () =>
        HttpResponse.json({
          id: 'abc123',
          title: 'A Video',
          description: null,
          channel_id: 'UC_x',
          channel_handle: null,
          published_at: '2026-01-01T00:00:00Z',
          duration_seconds: null,
          view_count: null,
          like_count: null,
          comment_count: null,
          tags: [],
          thumbnail_url: null,
          score: null,
          predicted_label: null,
          model_name: null,
          model_version: null,
          nlp_features: null,
          vision_features: null,
          similar_videos: [],
        }),
      ),
    )
    renderAt('/videos/abc123')
    expect(await screen.findByText('A Video')).toBeInTheDocument()
  })

  it('renders the channel view page with the channelId param at /channels/:channelId', async () => {
    server.use(
      http.get('/api/channels/UC_x', () =>
        HttpResponse.json({
          id: 'UC_x',
          handle: '@channelx',
          title: 'Channel X',
          description: null,
          subscriber_count: null,
          video_count: null,
          view_count: null,
          last_ingested_at: null,
        }),
      ),
      http.get('/api/videos', () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    )
    renderAt('/channels/UC_x')
    expect(await screen.findByText('Channel X')).toBeInTheDocument()
  })

  it('renders the labeled videos page at /labeled', async () => {
    server.use(
      http.get('/api/labels', () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    )
    renderAt('/labeled')
    expect(await screen.findByText(/no labeled videos match these filters/i)).toBeInTheDocument()
  })

  it('renders a not-found page for an unknown path', () => {
    renderAt('/something/nonexistent')
    expect(screen.getByText(/page not found/i)).toBeInTheDocument()
  })

  it('navigates between pages via the nav links', async () => {
    mockEmptyVideoList()
    mockEmptyLabelPool()
    const user = userEvent.setup()
    renderAt('/')
    await screen.findByText(/no videos match these filters/i)

    await user.click(screen.getByRole('link', { name: 'Label' }))
    expect(await screen.findByText(/no channels available to label/i)).toBeInTheDocument()

    await user.click(screen.getByRole('link', { name: 'Videos' }))
    expect(await screen.findByText(/no videos match these filters/i)).toBeInTheDocument()
  })
})
