import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

// Handlers are registered per-test-file (via server.use(...)). The one default below is for
// GET /config, which the layout and the video grid request on every render; without it
// every test would have to register it ('onUnhandledRequest: error' in setup.ts). The
// default is a normal, writable deployment; tests of read-only mode override it.
export const server = setupServer(http.get('/api/config', () => HttpResponse.json({ read_only: false })))
