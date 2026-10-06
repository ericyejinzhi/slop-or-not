import { useState, type FormEvent } from 'react'
import { useCreateIngest } from '../api/hooks'

export function IngestForm() {
  const [channel, setChannel] = useState('')
  const { mutate, isPending, isSuccess, isError, data, reset } = useCreateIngest()

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = channel.trim()
    if (!trimmed) return
    mutate({ channel: trimmed })
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white p-3"
    >
      <label className="text-sm text-slate-600" htmlFor="ingest-channel">
        Ingest a channel
      </label>
      <input
        id="ingest-channel"
        type="text"
        placeholder="@channelhandle or UC..."
        className="flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
        value={channel}
        onChange={(event) => {
          setChannel(event.target.value)
          if (isSuccess || isError) reset()
        }}
      />
      <button
        type="submit"
        className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
        disabled={isPending || channel.trim() === ''}
      >
        {isPending ? 'Starting...' : 'Ingest'}
      </button>
      {isSuccess && data && (
        <p className="w-full text-sm text-green-700">
          Ingestion started for {data.target}. It runs in the background: videos are fetched
          first, then analyzed and scored, which can take a few minutes - reload to see new
          scores.
        </p>
      )}
      {isError && (
        <p className="w-full text-sm text-red-600">Failed to start ingestion. Try again.</p>
      )}
    </form>
  )
}
