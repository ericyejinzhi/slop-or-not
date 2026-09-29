import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { VideoListItem, VideoListResponse } from '../api/types'
import { server } from '../test/mocks/server'
import { createWrapper } from '../test/queryClientWrapper'
import { VideoGridPage } from './VideoGridPage'

function renderPage() {
  const Wrapper = createWrapper()
  return render(
    <Wrapper>
      <MemoryRouter>
        <VideoGridPage />
      </MemoryRouter>
    </Wrapper>,
  )
}

function makeVideo(overrides: Partial<VideoListItem> = {}): VideoListItem {
  return {
    id: 'video_1',
    title: 'A Test Video',
    channel_id: 'UC_x',
    channel_handle: '@testchannel',
    published_at: '2026-01-01T00:00:00Z',
    view_count: 1234,
    thumbnail_url: null,
    score: null,
    predicted_label: null,
    ...overrides,
  }
}

describe('VideoGridPage', () => {
  it('renders video cards from the API response', async () => {
    const response: VideoListResponse = {
      items: [makeVideo({ score: 0.8, predicted_label: 'down' })],
      total: 1,
      limit: 20,
      offset: 0,
    }
    server.use(http.get('/api/videos', () => HttpResponse.json(response)))

    renderPage()

    expect(await screen.findByText('A Test Video')).toBeInTheDocument()
    expect(screen.getByText('@testchannel')).toBeInTheDocument()
    expect(screen.getByText('down (0.80)')).toBeInTheDocument()
    expect(screen.getByText('1,234 views')).toBeInTheDocument()
  })

  it('shows a message when no videos match the filters', async () => {
    server.use(
      http.get('/api/videos', () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    )
    renderPage()
    expect(await screen.findByText(/no videos match these filters/i)).toBeInTheDocument()
  })

  it('shows an error message when the request fails', async () => {
    server.use(
      http.get('/api/videos', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
    )
    renderPage()
    expect(await screen.findByText(/failed to load videos/i)).toBeInTheDocument()
  })

  it('requests the next page with an increased offset', async () => {
    const capturedUrls: string[] = []
    server.use(
      http.get('/api/videos', ({ request }) => {
        capturedUrls.push(request.url)
        return HttpResponse.json({
          items: [makeVideo()],
          total: 50,
          limit: 20,
          offset: 0,
        })
      }),
    )
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('A Test Video')
    await user.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() => {
      expect(capturedUrls.some((url) => url.includes('offset=20'))).toBe(true)
    })
  })

  it('disables Previous on the first page', async () => {
    server.use(
      http.get('/api/videos', () =>
        HttpResponse.json({ items: [makeVideo()], total: 1, limit: 20, offset: 0 }),
      ),
    )
    renderPage()
    await screen.findByText('A Test Video')
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
  })

  it('requests predicted_label=down when the filter is changed', async () => {
    const capturedUrls: string[] = []
    server.use(
      http.get('/api/videos', ({ request }) => {
        capturedUrls.push(request.url)
        return HttpResponse.json({ items: [makeVideo()], total: 1, limit: 20, offset: 0 })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('A Test Video')

    await user.selectOptions(screen.getByLabelText('Filter'), 'down')

    await waitFor(() => {
      expect(capturedUrls.some((url) => url.includes('predicted_label=down'))).toBe(true)
    })
  })
})
