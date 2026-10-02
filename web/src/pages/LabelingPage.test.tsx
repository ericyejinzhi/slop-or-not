import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import type { ChannelBatchPoolItem, LabelPoolItem } from '../api/types'
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

function makeChannelBatch(overrides: Partial<ChannelBatchPoolItem> = {}): ChannelBatchPoolItem {
  return {
    channel_id: 'UC_x',
    channel_handle: '@testchannel',
    videos: [
      makePoolItem({ video_id: 'video_1', title: 'Batch Video One' }),
      makePoolItem({ video_id: 'video_2', title: 'Batch Video Two' }),
    ],
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
})

describe('LabelingPage - channel mode (default)', () => {
  it('shows "no channels available" when the pool is empty', async () => {
    server.use(http.get('/api/labels/channel-pool', () => HttpResponse.json({ items: [] })))
    renderPage()
    expect(await screen.findByText(/no channels available to label/i)).toBeInTheDocument()
  })

  // Same rationale as the video-mode fixture below: the real backend's exclude_labeled
  // means a refetch after labeling the whole batch genuinely returns [].
  function channelPoolOnceThenEmpty() {
    let calls = 0
    return http.get('/api/labels/channel-pool', () => {
      calls += 1
      return HttpResponse.json({ items: calls === 1 ? [makeChannelBatch()] : [] })
    })
  }

  it('renders every video in the channel batch and posts one batch label for all of them', async () => {
    server.use(channelPoolOnceThenEmpty())
    let capturedBody: unknown
    server.use(
      http.post('/api/labels/batch', async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(
          {
            channel_id: 'UC_x',
            labeler: 'alice',
            label: 'up',
            video_count: 2,
            created_at: 'x',
          },
          { status: 201 },
        )
      }),
    )
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Batch Video One')
    expect(screen.getByText('Batch Video Two')).toBeInTheDocument()
    expect(screen.getByText('@testchannel')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Labeler'), 'alice')
    await user.click(screen.getByRole('button', { name: '(y) Up' }))

    expect(
      await screen.findByText(/no more channels available to label/i),
    ).toBeInTheDocument()
    expect(capturedBody).toEqual({
      channel_id: 'UC_x',
      video_ids: ['video_1', 'video_2'],
      label: 'up',
      labeler: 'alice',
    })
    expect(screen.getByText('Labeled 2 this session')).toBeInTheDocument()
  })

  it('submits a "down" batch label when the "n" key is pressed', async () => {
    server.use(channelPoolOnceThenEmpty())
    let capturedBody: unknown
    server.use(
      http.post('/api/labels/batch', async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json(
          { channel_id: 'UC_x', labeler: '', label: 'down', video_count: 2, created_at: 'x' },
          { status: 201 },
        )
      }),
    )
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Batch Video One')
    await user.keyboard('n')

    await screen.findByText(/no more channels available to label/i)
    expect(capturedBody).toMatchObject({ channel_id: 'UC_x', label: 'down' })
  })

  it('shows an error message when the channel pool fails to load', async () => {
    server.use(
      http.get('/api/labels/channel-pool', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderPage()
    expect(await screen.findByText(/failed to load the labeling pool/i)).toBeInTheDocument()
  })
})

describe('LabelingPage - video mode', () => {
  async function switchToVideoMode() {
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'By video' }))
    return user
  }

  it('shows "no videos available" when the pool is empty', async () => {
    server.use(http.get('/api/labels/channel-pool', () => HttpResponse.json({ items: [] })))
    server.use(http.get('/api/labels/pool', () => HttpResponse.json({ items: [] })))
    renderPage()
    await screen.findByText(/no channels available to label/i)

    await switchToVideoMode()

    expect(await screen.findByText(/no videos available to label/i)).toBeInTheDocument()
  })

  // The backend's exclude_labeled means a refetch after labeling everything genuinely
  // returns []; this mock simulates that (item on the first call, empty afterward) so
  // the auto-refill effect has something real to settle on instead of looping forever.
  function poolOnceThenEmpty() {
    let calls = 0
    return http.get('/api/labels/pool', () => {
      calls += 1
      return HttpResponse.json({ items: calls === 1 ? [makePoolItem()] : [] })
    })
  }

  it('renders the first pool video and submits an "up" label on click', async () => {
    server.use(http.get('/api/labels/channel-pool', () => HttpResponse.json({ items: [] })))
    server.use(poolOnceThenEmpty())
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
    renderPage()
    const user = await switchToVideoMode()

    await screen.findByText('Pool Video One')
    await user.type(screen.getByLabelText('Labeler'), 'alice')
    await user.click(screen.getByRole('button', { name: '(y) Up' }))

    expect(await screen.findByText(/no more videos available to label/i)).toBeInTheDocument()
    expect(capturedBody).toEqual({ video_id: 'video_1', label: 'up', labeler: 'alice' })
  })

  it('submits a "down" label when the "n" key is pressed', async () => {
    server.use(http.get('/api/labels/channel-pool', () => HttpResponse.json({ items: [] })))
    server.use(poolOnceThenEmpty())
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
    renderPage()
    const user = await switchToVideoMode()

    await screen.findByText('Pool Video One')
    await user.keyboard('n')

    await screen.findByText(/no more videos available to label/i)
    expect(capturedBody).toMatchObject({ video_id: 'video_1', label: 'down' })
  })

  it('auto-refills and keeps labeling once the fetched pool runs out', async () => {
    server.use(http.get('/api/labels/channel-pool', () => HttpResponse.json({ items: [] })))
    server.use(poolOnceThenEmpty())
    server.use(
      http.post('/api/labels', () =>
        HttpResponse.json(
          { video_id: 'video_1', labeler: '', label: 'skip', notes: null, created_at: 'x' },
          { status: 201 },
        ),
      ),
    )
    renderPage()
    const user = await switchToVideoMode()

    await screen.findByText('Pool Video One')
    await user.click(screen.getByRole('button', { name: '(s) Skip' }))

    expect(
      await screen.findByText(/no more videos available to label right now/i),
    ).toBeInTheDocument()
    expect(screen.getByText('Labeled 1 this session')).toBeInTheDocument()
  })

  it('shows an error message when the pool fails to load', async () => {
    server.use(http.get('/api/labels/channel-pool', () => HttpResponse.json({ items: [] })))
    server.use(
      http.get('/api/labels/pool', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
    )
    renderPage()
    await switchToVideoMode()

    expect(await screen.findByText(/failed to load the labeling pool/i)).toBeInTheDocument()
  })
})

describe('LabelingPage - shared chrome', () => {
  it('persists the labeler name to localStorage regardless of mode', async () => {
    server.use(http.get('/api/labels/channel-pool', () => HttpResponse.json({ items: [] })))
    const user = userEvent.setup()
    renderPage()

    await screen.findByText(/no channels available to label/i)
    await user.type(screen.getByLabelText('Labeler'), 'bob')

    expect(localStorage.getItem('slop-or-not:labeler')).toBe('bob')
  })
})
