import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { ChannelListItem, ChannelListResponse } from '../api/types'
import { server } from '../test/mocks/server'
import { createWrapper } from '../test/queryClientWrapper'
import { ChannelsPage } from './ChannelsPage'

function renderPage() {
  const Wrapper = createWrapper()
  return render(
    <Wrapper>
      <MemoryRouter>
        <ChannelsPage />
      </MemoryRouter>
    </Wrapper>,
  )
}

function makeChannel(overrides: Partial<ChannelListItem> = {}): ChannelListItem {
  return {
    id: 'UC_a',
    handle: '@alpha',
    title: 'Alpha Channel',
    subscriber_count: 12345,
    ingested_video_count: 10,
    scored_video_count: 10,
    channel_score: 0.81,
    channel_predicted_label: 'down',
    ...overrides,
  }
}

function respondWith(items: ChannelListItem[], total = items.length) {
  const response: ChannelListResponse = { items, total, limit: 20, offset: 0 }
  return http.get('/api/channels', () => HttpResponse.json(response))
}

describe('ChannelsPage', () => {
  it('lists channels with their score, scored/ingested counts and subscribers', async () => {
    server.use(
      respondWith([
        makeChannel(),
        makeChannel({
          id: 'UC_b',
          handle: '@beta',
          title: 'Beta Channel',
          channel_score: 0.12,
          channel_predicted_label: 'up',
          scored_video_count: 7,
          subscriber_count: null,
        }),
      ]),
    )
    renderPage()

    expect(await screen.findByText('Alpha Channel')).toBeInTheDocument()
    expect(screen.getByText('down (0.81)')).toBeInTheDocument()
    expect(screen.getByText('up (0.12)')).toBeInTheDocument()
    expect(screen.getByText('7 / 10')).toBeInTheDocument()
    expect(screen.getByText('12,345')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Alpha Channel' })).toHaveAttribute(
      'href',
      '/channels/UC_a',
    )
    expect(screen.getByText('1-2 of 2')).toBeInTheDocument()
  })

  it('shows Unscored for a channel with no scored videos', async () => {
    server.use(
      respondWith([
        makeChannel({ channel_score: null, channel_predicted_label: null, scored_video_count: 0 }),
      ]),
    )
    renderPage()

    expect(await screen.findByText('Unscored')).toBeInTheDocument()
  })

  it('shows an empty state when nothing matches', async () => {
    server.use(respondWith([]))
    renderPage()

    expect(await screen.findByText('No channels match these filters.')).toBeInTheDocument()
    expect(screen.getByText('0 channels')).toBeInTheDocument()
  })

  it('shows an error message when the request fails', async () => {
    server.use(http.get('/api/channels', () => new HttpResponse(null, { status: 500 })))
    renderPage()

    expect(await screen.findByText('Failed to load channels.')).toBeInTheDocument()
  })

  it('requests score-descending by default and sends the chosen filter', async () => {
    const urls: string[] = []
    server.use(
      http.get('/api/channels', ({ request }) => {
        urls.push(request.url)
        return HttpResponse.json({ items: [makeChannel()], total: 1, limit: 20, offset: 0 })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Alpha Channel')

    expect(urls[0]).toContain('sort=score')
    expect(urls[0]).toContain('order=desc')
    expect(urls[0]).not.toContain('predicted_label')

    await user.selectOptions(screen.getByLabelText('Show'), 'down')

    await waitFor(() => {
      expect(urls.some((url) => url.includes('predicted_label=down'))).toBe(true)
    })
  })

  it('goes back to the first page when a control changes', async () => {
    const urls: string[] = []
    server.use(
      http.get('/api/channels', ({ request }) => {
        urls.push(request.url)
        return HttpResponse.json({
          items: [makeChannel()],
          total: 100,
          limit: 20,
          offset: Number(new URL(request.url).searchParams.get('offset')),
        })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Alpha Channel')

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(urls.some((u) => u.includes('offset=20'))).toBe(true))

    await user.selectOptions(screen.getByLabelText('Order'), 'asc')
    await waitFor(() => {
      const last = urls[urls.length - 1]
      expect(last).toContain('order=asc')
      expect(last).toContain('offset=0')
    })
  })
})
