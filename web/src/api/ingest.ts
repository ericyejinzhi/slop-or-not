import { post } from './client'
import type { IngestRequest, IngestResponse } from './types'

export function createIngest(body: IngestRequest): Promise<IngestResponse> {
  return post<IngestResponse>('/ingest', body)
}
