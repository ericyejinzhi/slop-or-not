import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useChannels } from '../api/hooks'
import type { ListChannelsParams } from '../api/channels'
import { ScoreBadge } from '../components/ScoreBadge'
import { formatCount } from '../lib/format'

const PAGE_SIZE = 20

type SortOption = NonNullable<ListChannelsParams['sort']>
type OrderOption = NonNullable<ListChannelsParams['order']>
type LabelFilter = 'all' | 'down' | 'up'

export function ChannelsPage() {
  const [sort, setSort] = useState<SortOption>('score')
  const [order, setOrder] = useState<OrderOption>('desc')
  const [labelFilter, setLabelFilter] = useState<LabelFilter>('all')
  const [offset, setOffset] = useState(0)

  const { data, isLoading, isError } = useChannels({
    limit: PAGE_SIZE,
    offset,
    sort,
    order,
    predicted_label: labelFilter === 'all' ? undefined : labelFilter,
  })

  // Any control change goes back to the first page; staying on page 5 of a different
  // ordering would be meaningless.
  function change<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value)
      setOffset(0)
    }
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Channels</h1>
        <p className="text-sm text-slate-600">
          A channel&apos;s score is the average of its videos&apos; scores. Higher means more
          likely slop.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <label className="text-sm text-slate-600">
          Sort{' '}
          <select
            className="ml-1 rounded border border-slate-300 px-2 py-1 text-sm"
            value={sort}
            onChange={(event) => change(setSort)(event.target.value as SortOption)}
          >
            <option value="score">Score</option>
            <option value="title">Name</option>
            <option value="subscriber_count">Subscribers</option>
            <option value="ingested_video_count">Videos</option>
          </select>
        </label>
        <label className="text-sm text-slate-600">
          Order{' '}
          <select
            className="ml-1 rounded border border-slate-300 px-2 py-1 text-sm"
            value={order}
            onChange={(event) => change(setOrder)(event.target.value as OrderOption)}
          >
            <option value="desc">Descending</option>
            <option value="asc">Ascending</option>
          </select>
        </label>
        <label className="text-sm text-slate-600">
          Show{' '}
          <select
            className="ml-1 rounded border border-slate-300 px-2 py-1 text-sm"
            value={labelFilter}
            onChange={(event) => change(setLabelFilter)(event.target.value as LabelFilter)}
          >
            <option value="all">All channels</option>
            <option value="down">Predicted slop</option>
            <option value="up">Predicted not slop</option>
          </select>
        </label>
      </div>

      {isLoading && <p className="text-slate-600">Loading channels...</p>}
      {isError && <p className="text-red-600">Failed to load channels.</p>}

      {!isLoading && !isError && (
        <>
          {items.length === 0 ? (
            <p className="text-slate-600">No channels match these filters.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-2 pr-4 font-medium">Channel</th>
                  <th className="py-2 pr-4 font-medium">Score</th>
                  <th className="py-2 pr-4 font-medium">Videos scored</th>
                  <th className="py-2 font-medium">Subscribers</th>
                </tr>
              </thead>
              <tbody>
                {items.map((channel) => (
                  <tr key={channel.id} className="border-b border-slate-100">
                    <td className="py-2 pr-4">
                      <Link
                        to={`/channels/${channel.id}`}
                        className="font-medium text-slate-900 hover:underline"
                      >
                        {channel.title}
                      </Link>
                      {channel.handle && (
                        <span className="ml-2 text-xs text-slate-500">{channel.handle}</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      <ScoreBadge
                        score={channel.channel_score}
                        predictedLabel={channel.channel_predicted_label}
                      />
                    </td>
                    <td className="py-2 pr-4 text-slate-600">
                      {channel.scored_video_count} / {channel.ingested_video_count}
                    </td>
                    <td className="py-2 text-slate-600">
                      {formatCount(channel.subscriber_count)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0}
            >
              Previous
            </button>
            <span className="text-sm text-slate-500">
              {total === 0
                ? '0 channels'
                : `${offset + 1}-${Math.min(offset + PAGE_SIZE, total)} of ${total}`}
            </span>
            <button
              type="button"
              className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}
