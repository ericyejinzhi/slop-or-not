import { post } from './client'
import type { PredictRequest, PredictResponse } from './types'

export function createPrediction(body: PredictRequest): Promise<PredictResponse> {
  return post<PredictResponse>('/predict', body)
}
