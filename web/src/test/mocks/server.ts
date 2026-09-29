import { setupServer } from 'msw/node'

// Handlers are registered per-test-file (via server.use(...)) or added here as the API
// client grows in later stages - kept empty for now since no API client exists yet.
export const server = setupServer()
