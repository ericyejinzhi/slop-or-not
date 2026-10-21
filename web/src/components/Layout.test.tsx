import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { server } from '../test/mocks/server'
import { createWrapper } from '../test/queryClientWrapper'
import { Layout } from './Layout'

function renderLayout() {
  const Wrapper = createWrapper()
  return render(
    <Wrapper>
      <MemoryRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<div>home page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </Wrapper>,
  )
}

describe('Layout navigation', () => {
  it('shows the labeling links on a normal deployment', async () => {
    renderLayout()

    expect(await screen.findByRole('link', { name: 'Label' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Labeled' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Videos' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Channels' })).toBeInTheDocument()
  })

  it('hides the labeling links on a read-only deployment but keeps Videos', async () => {
    server.use(http.get('/api/config', () => HttpResponse.json({ read_only: true })))
    renderLayout()

    // shown until the config arrives (fail open), then removed
    await waitFor(() => {
      expect(screen.queryByRole('link', { name: 'Label' })).not.toBeInTheDocument()
    })
    expect(screen.queryByRole('link', { name: 'Labeled' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Videos' })).toBeInTheDocument()
    // the ranked channel list only reads, so it stays available in a read-only deployment
    expect(screen.getByRole('link', { name: 'Channels' })).toBeInTheDocument()
  })

  it('shows the Check a video link only when the server can make predictions', async () => {
    const { unmount } = renderLayout()
    await screen.findByRole('link', { name: 'Videos' })
    expect(screen.queryByRole('link', { name: 'Check a video' })).not.toBeInTheDocument()
    unmount()

    server.use(
      http.get('/api/config', () =>
        HttpResponse.json({ read_only: true, predict_enabled: true }),
      ),
    )
    renderLayout()

    expect(await screen.findByRole('link', { name: 'Check a video' })).toHaveAttribute(
      'href',
      '/check',
    )
  })

  it('keeps the links if the config request fails (the API enforces read-only itself)', async () => {
    let asked = false
    server.use(
      http.get('/api/config', () => {
        asked = true
        return new HttpResponse(null, { status: 500 })
      }),
    )
    renderLayout()

    await waitFor(() => expect(asked).toBe(true))
    expect(screen.getByRole('link', { name: 'Label' })).toBeInTheDocument()
  })
})
