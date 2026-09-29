import { QueryClient } from '@tanstack/react-query'

// A factory (not a shared singleton) so tests can create an isolated client per test
// instead of sharing cached query state across test cases.
export function createQueryClient(overrides?: { retry?: boolean | number }): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: overrides?.retry ?? 1,
      },
    },
  })
}
