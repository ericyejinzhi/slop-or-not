import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import type { LabeledVideoItem } from '../api/types'
import { server } from '../test/mocks/server'
import { createWrapper } from '../test/queryClientWrapper'
import { LabeledVideosPage } from './LabeledVideosPage'

function renderPage() {
  const Wrapper = createWrapper()
  return render(
    <Wrapper>
      <LabeledVideosPage />
    </Wrapper>,
  )
}

function makeItem(overrides: Partial<LabeledVideoItem> = {}): LabeledVideoItem {
  return {
    video_id: 'video_1',
    title: 'Labeled Video One',
    channel_id: 'UC_x',
    channel_handle: '@testchannel',
    thumbnail_url: null,
    label: 'down',
    labeler: 'alice',
    labeled_at: '2026-01-01T00:00:00Z',
    label_count: 1,
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
})

describe('LabeledVideosPage', () => {
  it('shows "no labeled videos" when there are none', async () => {
    server.use(
      http.get('/api/labels', () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    )
    renderPage()
    expect(
      await screen.findByText(/no labeled videos match these filters/i),
    ).toBeInTheDocument()
  })

  it('renders labeled videos with their current label and history', async () => {
    server.use(
      http.get('/api/labels', () =>
        HttpResponse.json({ items: [makeItem({ label_count: 3 })], total: 1, limit: 20, offset: 0 }),
      ),
    )
    renderPage()

    expect(await screen.findByText('Labeled Video One')).toBeInTheDocument()
    expect(screen.getByText('down')).toBeInTheDocument()
    expect(screen.getByText(/labeled 3 times/i)).toBeInTheDocument()
    expect(screen.getByText(/last by alice/i)).toBeInTheDocument()
  })

  it('sends the search text as a query param after debouncing', async () => {
    let capturedUrl: URL | undefined
    server.use(
      http.get('/api/labels', ({ request }) => {
        capturedUrl = new URL(request.url)
        return HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 })
      }),
    )
    const user = userEvent.setup()
    renderPage()

    await screen.findByText(/no labeled videos match these filters/i)
    await user.type(screen.getByPlaceholderText(/search by title/i), 'mole')

    await waitFor(() => expect(capturedUrl?.searchParams.get('q')).toBe('mole'))
  })

  it('sends the selected label filter as a query param', async () => {
    let capturedUrl: URL | undefined
    server.use(
      http.get('/api/labels', ({ request }) => {
        capturedUrl = new URL(request.url)
        return HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 })
      }),
    )
    const user = userEvent.setup()
    renderPage()

    await screen.findByText(/no labeled videos match these filters/i)
    await user.selectOptions(screen.getByRole('combobox'), 'up')

    await waitFor(() => expect(capturedUrl?.searchParams.get('label')).toBe('up'))
  })

  it('relabels a video via the inline buttons', async () => {
    server.use(
      http.get('/api/labels', () =>
        HttpResponse.json({ items: [makeItem()], total: 1, limit: 20, offset: 0 }),
      ),
    )
    let capturedBody: unknown
    server.use(
      http.post('/api/labels', async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(
          { video_id: 'video_1', labeler: '', label: 'up', notes: null, created_at: 'x' },
          { status: 201 },
        )
      }),
    )
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Labeled Video One')
    await user.click(screen.getByRole('button', { name: 'Up' }))

    await waitFor(() => expect(capturedBody).toMatchObject({ video_id: 'video_1', label: 'up' }))
  })

  it('shows an error message when loading fails', async () => {
    server.use(
      http.get('/api/labels', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
    )
    renderPage()
    expect(await screen.findByText(/failed to load labeled videos/i)).toBeInTheDocument()
  })
})
