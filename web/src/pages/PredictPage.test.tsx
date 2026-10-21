import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { PredictResponse } from '../api/types'
import { server } from '../test/mocks/server'
import { createWrapper } from '../test/queryClientWrapper'
import { PredictPage } from './PredictPage'

const RESULT: PredictResponse = {
  video_id: 'dQw4w9WgXcQ',
  title: 'You Wont BELIEVE This',
  thumbnail_url: 'https://img.example/t.jpg',
  score: 0.81,
  predicted_label: 'down',
  factors: [
    {
      feature: 'title_caps_ratio',
      label: 'Share of the title in capitals',
      value: 0.4,
      contribution: 0.9,
    },
    { feature: 'tag_count', label: 'Number of tags', value: 12, contribution: -0.3 },
  ],
  similar_videos: [{ video_id: 'abc', title: 'A similar one', distance: 0.1, score: 0.7 }],
  channel: {
    channel_id: 'UC_x',
    title: 'Some Channel',
    in_dataset: false,
    channel_score: null,
    scored_video_count: 0,
  },
  model_name: 'xgboost',
  model_version: 'v1',
  comments_used: 87,
  warnings: [],
}

function enablePredictions() {
  server.use(
    http.get('/api/config', () =>
      HttpResponse.json({ read_only: true, predict_enabled: true }),
    ),
  )
}

function renderPage() {
  const Wrapper = createWrapper()
  return render(
    <Wrapper>
      <MemoryRouter>
        <PredictPage />
      </MemoryRouter>
    </Wrapper>,
  )
}

async function submit(link: string) {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('YouTube video link'), link)
  await user.click(screen.getByRole('button', { name: 'Check video' }))
  return user
}

describe('PredictPage', () => {
  it('says so, and offers no form, when the server cannot make predictions', async () => {
    renderPage()

    expect(await screen.findByText(/not available on this server/i)).toBeInTheDocument()
    expect(screen.queryByLabelText('YouTube video link')).not.toBeInTheDocument()
  })

  it('keeps the button disabled until something is pasted', async () => {
    enablePredictions()
    renderPage()

    expect(await screen.findByRole('button', { name: 'Check video' })).toBeDisabled()
  })

  it('sends the pasted link and shows the verdict, the score and what drove it', async () => {
    enablePredictions()
    let captured: unknown
    server.use(
      http.post('/api/predict', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json(RESULT)
      }),
    )
    renderPage()

    await submit('  https://youtu.be/dQw4w9WgXcQ  ')

    expect(await screen.findByTestId('verdict')).toHaveTextContent('Looks like slop')
    expect(captured).toEqual({ url: 'https://youtu.be/dQw4w9WgXcQ' })
    expect(screen.getByText('You Wont BELIEVE This')).toBeInTheDocument()
    expect(screen.getByText('Slop score: 81 out of 100')).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Slop score' })).toHaveAttribute(
      'aria-valuenow',
      '81',
    )
    expect(screen.getByText('Share of the title in capitals')).toBeInTheDocument()
    expect(screen.getByText('points toward slop')).toBeInTheDocument()
    expect(screen.getByText('points away from slop')).toBeInTheDocument()
    expect(screen.getByText(/not in the dataset/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'A similar one' })).toHaveAttribute(
      'href',
      '/videos/abc',
    )
    expect(screen.getByText(/nothing from this check is saved/i)).toBeInTheDocument()
  })

  it('shows the not-slop verdict and a known channel average', async () => {
    enablePredictions()
    server.use(
      http.post('/api/predict', () =>
        HttpResponse.json({
          ...RESULT,
          score: 0.12,
          predicted_label: 'up',
          channel: {
            ...RESULT.channel,
            in_dataset: true,
            channel_score: 0.64,
            scored_video_count: 10,
          },
        }),
      ),
    )
    renderPage()

    await submit('dQw4w9WgXcQ')

    expect(await screen.findByTestId('verdict')).toHaveTextContent("Doesn't look like slop")
    expect(screen.getByText(/average slop score across 10 scored videos is 64/i)).toBeInTheDocument()
  })

  it('lists the warnings the server reports', async () => {
    enablePredictions()
    server.use(
      http.post('/api/predict', () =>
        HttpResponse.json({ ...RESULT, warnings: ['This video has no comments.'] }),
      ),
    )
    renderPage()

    await submit('dQw4w9WgXcQ')

    expect(await screen.findByText('This video has no comments.')).toBeInTheDocument()
  })

  it('shows the server message when the link is not a video', async () => {
    enablePredictions()
    server.use(
      http.post('/api/predict', () =>
        HttpResponse.json({ detail: 'That does not look like a link.' }, { status: 422 }),
      ),
    )
    renderPage()

    await submit('hello')

    expect(await screen.findByRole('alert')).toHaveTextContent('That does not look like a link.')
  })

  it('shows the retry message when the rate limit is hit', async () => {
    enablePredictions()
    server.use(
      http.post('/api/predict', () =>
        HttpResponse.json({ detail: 'Too many predictions. Try again in about 5 minute(s).' }, { status: 429 }),
      ),
    )
    renderPage()

    await submit('dQw4w9WgXcQ')

    expect(await screen.findByRole('alert')).toHaveTextContent(/try again in about 5 minute/i)
  })

  it('falls back to a generic message when the server fails without a reason', async () => {
    enablePredictions()
    server.use(http.post('/api/predict', () => new HttpResponse(null, { status: 500 })))
    renderPage()

    await submit('dQw4w9WgXcQ')

    expect(await screen.findByRole('alert')).toHaveTextContent(/something went wrong/i)
  })

  it('clears the previous result once the link is edited', async () => {
    enablePredictions()
    server.use(http.post('/api/predict', () => HttpResponse.json(RESULT)))
    renderPage()

    const user = await submit('dQw4w9WgXcQ')
    await screen.findByTestId('verdict')

    await user.type(screen.getByLabelText('YouTube video link'), 'x')

    expect(screen.queryByTestId('verdict')).not.toBeInTheDocument()
  })

  it('shows progress while the check is running', async () => {
    enablePredictions()
    server.use(
      http.post('/api/predict', async () => {
        await new Promise((resolve) => setTimeout(resolve, 150))
        return HttpResponse.json(RESULT)
      }),
    )
    renderPage()

    await submit('dQw4w9WgXcQ')

    expect(await screen.findByRole('status')).toHaveTextContent(/up to a minute/i)
    expect(screen.getByRole('button', { name: 'Checking...' })).toBeDisabled()
    await screen.findByTestId('verdict')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
