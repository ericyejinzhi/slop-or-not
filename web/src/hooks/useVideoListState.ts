import { useState } from 'react'
import type { ListVideosParams } from '../api/videos'

export type SortOption = NonNullable<ListVideosParams['sort']>
export type OrderOption = NonNullable<ListVideosParams['order']>
export type PredictedLabelFilter = 'up' | 'down' | ''

export const PAGE_SIZE = 20

// Shared sort/order/filter/pagination state for any page that lists videos (the video
// grid, and a channel's own video list) - `fixedParams` merges in page-specific params
// (e.g. channel_id) that aren't user-controlled.
export function useVideoListState(fixedParams: Partial<ListVideosParams> = {}) {
  const [offset, setOffset] = useState(0)
  const [sort, setSortState] = useState<SortOption>('published_at')
  const [order, setOrderState] = useState<OrderOption>('desc')
  const [predictedLabel, setPredictedLabelState] = useState<PredictedLabelFilter>('')

  function setSort(value: SortOption) {
    setSortState(value)
    setOffset(0)
  }

  function setOrder(value: OrderOption) {
    setOrderState(value)
    setOffset(0)
  }

  function setPredictedLabel(value: PredictedLabelFilter) {
    setPredictedLabelState(value)
    setOffset(0)
  }

  const params: ListVideosParams = {
    limit: PAGE_SIZE,
    offset,
    sort,
    order,
    ...(predictedLabel ? { predicted_label: predictedLabel } : {}),
    ...fixedParams,
  }

  return {
    params,
    offset,
    setOffset,
    sort,
    setSort,
    order,
    setOrder,
    predictedLabel,
    setPredictedLabel,
  }
}
