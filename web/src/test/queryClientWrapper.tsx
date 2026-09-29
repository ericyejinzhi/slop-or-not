import { QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { createQueryClient } from '../queryClient'

// A fresh QueryClient per call, so tests don't share cached query state with each other.
// retry: false - the production default's retry-with-backoff would otherwise push a
// query past its error state well beyond findBy's default 1000ms timeout, since even one
// retry's delay (react-query's default backoff starts around 1s) is enough to time out
// an error-path test that's just waiting for isError to become true.
export function createWrapper() {
  const queryClient = createQueryClient({ retry: false })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}
