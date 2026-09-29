import { useParams } from 'react-router-dom'
import { useChannel, useVideos } from '../api/hooks'
import { VideoGrid } from '../components/VideoGrid'
import { VideoListControls } from '../components/VideoListControls'
import { PAGE_SIZE, useVideoListState } from '../hooks/useVideoListState'
import { formatCount, formatDate } from '../lib/format'

export function ChannelViewPage() {
  const { channelId } = useParams<{ channelId: string }>()
  const {
    data: channel,
    isLoading: isChannelLoading,
    isError: isChannelError,
  } = useChannel(channelId)

  const {
    params,
    offset,
    setOffset,
    sort,
    setSort,
    order,
    setOrder,
    predictedLabel,
    setPredictedLabel,
  } = useVideoListState({ channel_id: channelId })
  const {
    data: videoList,
    isLoading: isVideosLoading,
    isError: isVideosError,
  } = useVideos(params)

  if (isChannelLoading) {
    return <p className="text-slate-600">Loading channel...</p>
  }
  if (isChannelError || !channel) {
    return <p className="text-red-600">Failed to load this channel.</p>
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold text-slate-900">{channel.title}</h1>
        {channel.handle && <p className="text-sm text-slate-500">{channel.handle}</p>}
        {channel.description && (
          <p className="whitespace-pre-line text-sm text-slate-700">{channel.description}</p>
        )}
        <p className="text-sm text-slate-600">
          {formatCount(channel.subscriber_count)} subscribers {'·'}{' '}
          {formatCount(channel.video_count)} videos {'·'} {formatCount(channel.view_count)}{' '}
          views
        </p>
        <p className="text-xs text-slate-400">
          {channel.last_ingested_at
            ? `Last ingested ${formatDate(channel.last_ingested_at)}`
            : 'Never fully ingested'}
        </p>
      </div>

      <div className="space-y-4">
        <VideoListControls
          sort={sort}
          onSortChange={setSort}
          order={order}
          onOrderChange={setOrder}
          predictedLabel={predictedLabel}
          onPredictedLabelChange={setPredictedLabel}
        />
        <VideoGrid
          items={videoList?.items ?? []}
          total={videoList?.total ?? 0}
          offset={offset}
          pageSize={PAGE_SIZE}
          isLoading={isVideosLoading}
          isError={isVideosError}
          onPrevious={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          onNext={() => setOffset(offset + PAGE_SIZE)}
        />
      </div>
    </div>
  )
}
