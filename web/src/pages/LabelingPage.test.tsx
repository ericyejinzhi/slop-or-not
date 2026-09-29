import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import type { LabelPoolItem } from '../api/types'
import { server } from '../test/mocks/server'
import { createWrapper } from '../test/queryClientWrapper'
import { LabelingPage } from './LabelingPage'

function renderPage() {
  const Wrapper = createWrapper()
  return render(
    <Wrapper>
      <LabelingPage />
    </Wrapper>,
  )
}

function makePoolItem(overrides: Partial<LabelPoolItem> = {}): LabelPoolItem {
  return {
    video_id: 'video_1',
    title: 'Pool Video One',
    channel_id: 'UC_x',
    channel_handle: '@testchannel',
    published_at: '2026-01-01T00:00:00Z',
    duration_seconds: 300,
    view_count: 100,
    like_count: 10,
    comment_count: 2,
    thumbnail_url: null,
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
})

describe('LabelingPage', () => {
  it('shows "no videos available" when the pool is empty', async () => {
    server.use(http.get('/api/labels/pool', () => HttpResponse.json({ items: [] })))
    renderPage()
    expect(await screen.findByText(/no videos available to label/i)).toBeInTheDocument()
  })

  it('renders the first pool video and submits an "up" label on click', async () => {
    server.use(
      http.get('/api/labels/pool', () =>
        HttpResponse.json({ items: [makePoolItem()] }),
      ),
    )
    let capturedBody: unknown
    server.use(
      http.post('/api/labels', async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(
          { video_id: 'video_1', labeler: 'alice', label: 'up', notes: null, created_at: 'x' },
          { status: 201 },
        )
      }),
    )
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Pool Video One')
    await user.type(screen.getByLabelText('Labeler'), 'alice')
    await user.click(screen.getByRole('button', { name: '(y) Up' }))

    expect(await screen.findByText(/no videos available to label|pool complete/i)).toBeInTheDocument()
    expect(capturedBody).toEqual({ video_id: 'video_1', label: 'up', labeler: 'alice' })
  })

  it('submits a "down" label when the "n" key is pressed', async () => {
    server.use(
      http.get('/api/labels/pool', () => HttpResponse.json({ items: [makePoolItem()] })),
    )
    let capturedBody: unknown
    server.use(
      http.post('/api/labels', async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(
          { video_id: 'video_1', labeler: '', label: 'down', notes: null, created_at: 'x' },
          { status: 201 },
        )
      }),
    )
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Pool Video One')
    await user.keyboard('n')

    await screen.findByText(/pool complete|no videos available/i)
    expect(capturedBody).toMatchObject({ video_id: 'video_1', label: 'down' })
  })

  it('shows "pool complete" after labeling every video in the pool', async () => {
    server.use(
      http.get('/api/labels/pool', () => HttpResponse.json({ items: [makePoolItem()] })),
      http.post('/api/labels', () =>
        HttpResponse.json(
          { video_id: 'video_1', labeler: '', label: 'skip', notes: null, created_at: 'x' },
          { status: 201 },
        ),
      ),
    )
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Pool Video One')
    await user.click(screen.getByRole('button', { name: '(s) Skip' }))

    expect(await screen.findByText(/pool complete for this session/i)).toBeInTheDocument()
    expect(screen.getByText('Labeled 1 this session')).toBeInTheDocument()
  })

  it('persists the labeler name to localStorage', async () => {
    server.use(http.get('/api/labels/pool', () => HttpResponse.json({ items: [] })))
    const user = userEvent.setup()
    renderPage()

    await screen.findByText(/no videos available to label/i)
    await user.type(screen.getByLabelText('Labeler'), 'bob')

    expect(localStorage.getItem('slop-or-not:labeler')).toBe('bob')
  })

  it('shows an error message when the pool fails to load', async () => {
    server.use(
      http.get('/api/labels/pool', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
    )
    renderPage()
    expect(await screen.findByText(/failed to load the labeling pool/i)).toBeInTheDocument()
  })
})
