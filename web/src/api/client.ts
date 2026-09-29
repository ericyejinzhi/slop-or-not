// Thin fetch wrapper. BASE_URL is relative ('/api') so requests go through Vite's dev
// proxy (vite.config.ts) during `npm run dev`, avoiding CORS entirely - the backend
// never got CORSMiddleware added in Phase 5.
const BASE_URL = '/api'

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown) {
    super(`API request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => undefined)
    throw new ApiError(response.status, body)
  }

  return (await response.json()) as T
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path)
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

// Typed `object`, not `Record<string, ...>` - TS refuses to assign a named interface
// (e.g. ListVideosParams) to a parameter typed with a string index signature unless the
// interface declares one itself, which none of the *Params interfaces do. Casting
// internally on iteration sidesteps that without adding an index signature to every
// params interface just to satisfy this one helper.
export function buildQuery(params: object): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params) as [
    string,
    string | number | undefined,
  ][]) {
    if (value !== undefined) search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}
