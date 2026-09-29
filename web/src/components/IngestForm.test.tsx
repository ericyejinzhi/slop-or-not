import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/mocks/server'
import { createWrapper } from '../test/queryClientWrapper'
import { IngestForm } from './IngestForm'

function renderForm() {
  const Wrapper = createWrapper()
  return render(
    <Wrapper>
      <IngestForm />
    </Wrapper>,
  )
}

describe('IngestForm', () => {
  it('disables the submit button when the input is empty', () => {
    renderForm()
    expect(screen.getByRole('button', { name: 'Ingest' })).toBeDisabled()
  })

  it('submits the channel and shows a success message', async () => {
    let capturedBody: unknown
    server.use(
      http.post('/api/ingest', async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json({ status: 'accepted', target: '@somechannel' }, { status: 202 })
      }),
    )
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByLabelText('Ingest a channel'), '@somechannel')
    await user.click(screen.getByRole('button', { name: 'Ingest' }))

    expect(await screen.findByText(/ingestion started for @somechannel/i)).toBeInTheDocument()
    expect(capturedBody).toEqual({ channel: '@somechannel' })
  })

  it('shows an error message when the request fails', async () => {
    server.use(
      http.post('/api/ingest', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
    )
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByLabelText('Ingest a channel'), '@somechannel')
    await user.click(screen.getByRole('button', { name: 'Ingest' }))

    expect(await screen.findByText(/failed to start ingestion/i)).toBeInTheDocument()
  })

  it('clears the previous result message once the input changes again', async () => {
    server.use(
      http.post('/api/ingest', () =>
        HttpResponse.json({ status: 'accepted', target: '@somechannel' }, { status: 202 }),
      ),
    )
    const user = userEvent.setup()
    renderForm()

    const input = screen.getByLabelText('Ingest a channel')
    await user.type(input, '@somechannel')
    await user.click(screen.getByRole('button', { name: 'Ingest' }))
    await screen.findByText(/ingestion started/i)

    await user.type(input, '2')
    expect(screen.queryByText(/ingestion started/i)).not.toBeInTheDocument()
  })
})
