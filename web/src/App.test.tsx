import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import App from './App'
import { server } from './test/mocks/server'
import { createWrapper } from './test/queryClientWrapper'

describe('App', () => {
  it('renders the nav brand and the default page', async () => {
    server.use(
      http.get('/api/videos', () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    )
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <App />
      </Wrapper>,
    )
    expect(screen.getByText('slop-or-not')).toBeInTheDocument()
    expect(await screen.findByText(/no videos match these filters/i)).toBeInTheDocument()
  })
})
