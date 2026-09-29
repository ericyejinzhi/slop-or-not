import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { ApiError, buildQuery, get, post } from './client'
import { server } from '../test/mocks/server'

describe('buildQuery', () => {
  it('omits undefined values and encodes the rest', () => {
    expect(buildQuery({ limit: 20, channel_id: undefined, sort: 'score' })).toBe(
      '?limit=20&sort=score',
    )
  })

  it('returns an empty string for no params', () => {
    expect(buildQuery({})).toBe('')
  })
})

describe('get/post', () => {
  it('parses a successful JSON response', async () => {
    server.use(
      http.get('/api/ping', () => HttpResponse.json({ ok: true })),
    )
    const result = await get<{ ok: boolean }>('/ping')
    expect(result).toEqual({ ok: true })
  })

  it('sends a JSON body on post', async () => {
    server.use(
      http.post('/api/echo', async ({ request }) => {
        const body = await request.json()
        return HttpResponse.json(body)
      }),
    )
    const result = await post<{ label: string }>('/echo', { label: 'down' })
    expect(result).toEqual({ label: 'down' })
  })

  it('throws ApiError with the status and body on a non-2xx response', async () => {
    server.use(
      http.get('/api/broken', () =>
        HttpResponse.json({ detail: 'not found' }, { status: 404 }),
      ),
    )
    await expect(get('/broken')).rejects.toMatchObject({
      status: 404,
      body: { detail: 'not found' },
    })
  })

  it('is an instance of ApiError', async () => {
    server.use(http.get('/api/broken', () => new HttpResponse(null, { status: 500 })))
    await expect(get('/broken')).rejects.toBeInstanceOf(ApiError)
  })
})
