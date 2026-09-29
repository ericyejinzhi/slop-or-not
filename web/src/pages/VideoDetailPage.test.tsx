import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { VideoDetail } from '../api/types'
import { server } from '../test/mocks/server'
import { createWrapper } from '../test/queryClientWrapper'
import { VideoDetailPage } from './VideoDetailPage'

function renderAtVideo(videoId: string) {
  const Wrapper = createWrapper()
  return render(
    <Wrapper>
      <MemoryRouter initialEntries={[`/videos/${videoId}`]}>
        <Routes>
          <Route path="/videos/:videoId" element={<VideoDetailPage />} />
        </Routes>
      </MemoryRouter>
    </Wrapper>,
  )
}

function makeDetail(overrides: Partial<VideoDetail> = {}): VideoDetail {
  return {
    id: 'video_1',
    title: 'A Fully Featured Video',
    description: 'A description of the video.',
    channel_id: 'UC_x',
    channel_handle: '@testchannel',
    published_at: '2026-01-01T00:00:00Z',
    duration_seconds: 600,
    view_count: 1000,
    like_count: 50,
    comment_count: 5,
    tags: ['tag-a', 'tag-b'],
    thumbnail_url: null,
    score: 0.87,
    predicted_label: 'down',
    model_name: 'xgboost',
    model_version: 'v1',
    nlp_features: null,
    vision_features: null,
    similar_videos: [],
    ...overrides,
  }
}

describe('VideoDetailPage', () => {
  it('renders title, channel link, score, and metadata', async () => {
    server.use(http.get('/api/videos/video_1', () => HttpResponse.json(makeDetail())))
    renderAtVideo('video_1')

    expect(await screen.findByText('A Fully Featured Video')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '@testchannel' })).toHaveAttribute(
      'href',
      '/channels/UC_x',
    )
    expect(screen.getByText('down (0.87)')).toBeInTheDocument()
    expect(screen.getByText(/1,000 views/)).toBeInTheDocument()
    expect(screen.getByText('A description of the video.')).toBeInTheDocument()
    expect(screen.getByText('tag-a, tag-b')).toBeInTheDocument()
  })

  it('shows "not computed yet" when nlp/vision features are null', async () => {
    server.use(http.get('/api/videos/video_1', () => HttpResponse.json(makeDetail())))
    renderAtVideo('video_1')

    await screen.findByText('A Fully Featured Video')
    expect(screen.getAllByText(/not computed yet for this video/i)).toHaveLength(2)
  })

  it('renders the nlp/vision feature breakdown when present', async () => {
    server.use(
      http.get('/api/videos/video_1', () =>
        HttpResponse.json(
          makeDetail({
            nlp_features: {
              comment_count_scored: 10,
              sentiment_mean: 0.5,
              sentiment_std: 0.2,
              sentiment_negative_share: 0.1,
              slop_keyword_rate: 0.05,
              topic_cluster_count: 3,
              topic_top_cluster_share: 0.4,
              topic_top_cluster_sentiment: 0.3,
              topic_sentiment_spread: 0.15,
              title_lure_score: 0.6,
              title_mysterious_score: 0.2,
              title_transparent_score: 0.1,
            },
            vision_features: {
              clip_clickbait_score: 0.3,
              clip_ai_generated_score: 0.2,
              clip_text_heavy_score: 0.4,
            },
          }),
        ),
      ),
    )
    renderAtVideo('video_1')

    await screen.findByText('A Fully Featured Video')
    expect(screen.getByText('Sentiment mean')).toBeInTheDocument()
    expect(screen.getByText('0.50')).toBeInTheDocument()
    expect(screen.getByText('Clickbait score')).toBeInTheDocument()
    expect(screen.getByText('0.30')).toBeInTheDocument()
  })

  it('renders the similar videos strip', async () => {
    server.use(
      http.get('/api/videos/video_1', () =>
        HttpResponse.json(
          makeDetail({
            similar_videos: [
              { video_id: 'video_2', distance: 0.04, title: 'A Similar Video', thumbnail_url: null },
            ],
          }),
        ),
      ),
    )
    renderAtVideo('video_1')

    await screen.findByText('A Fully Featured Video')
    expect(screen.getByText('A Similar Video')).toBeInTheDocument()
    expect(screen.getByText('distance 0.040')).toBeInTheDocument()
  })

  it('shows an error message when the request fails', async () => {
    server.use(
      http.get('/api/videos/video_1', () => HttpResponse.json({ detail: 'not found' }, { status: 404 })),
    )
    renderAtVideo('video_1')

    expect(await screen.findByText(/failed to load this video/i)).toBeInTheDocument()
  })
})
