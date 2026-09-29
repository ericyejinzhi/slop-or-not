import { useVideos } from '../api/hooks'
import { IngestForm } from '../components/IngestForm'
import { VideoGrid } from '../components/VideoGrid'
import { VideoListControls } from '../components/VideoListControls'
import { PAGE_SIZE, useVideoListState } from '../hooks/useVideoListState'

export function VideoGridPage() {
  const { params, offset, setOffset, sort, setSort, order, setOrder, predictedLabel, setPredictedLabel } =
    useVideoListState()

  const { data, isLoading, isError } = useVideos(params)

  return (
    <div className="space-y-4">
      <IngestForm />

      <VideoListControls
        sort={sort}
        onSortChange={setSort}
        order={order}
        onOrderChange={setOrder}
        predictedLabel={predictedLabel}
        onPredictedLabelChange={setPredictedLabel}
      />

      <VideoGrid
        items={data?.items ?? []}
        total={data?.total ?? 0}
        offset={offset}
        pageSize={PAGE_SIZE}
        isLoading={isLoading}
        isError={isError}
        onPrevious={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        onNext={() => setOffset(offset + PAGE_SIZE)}
      />
    </div>
  )
}
