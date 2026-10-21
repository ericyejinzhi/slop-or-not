import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { usePredict, usePredictEnabled } from '../api/hooks'
import { PredictionResultCard } from '../components/PredictionResultCard'

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string') return detail
    if (error.status === 422) return 'Paste the link of a single YouTube video.'
  }
  return 'Something went wrong. Try again in a moment.'
}

export function PredictPage() {
  const [link, setLink] = useState('')
  const enabled = usePredictEnabled()
  const { mutate, isPending, isError, error, data, reset } = usePredict()

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = link.trim()
    if (!trimmed || isPending) return
    mutate({ url: trimmed })
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Is this video slop?</h1>
        <p className="mt-1 text-sm text-slate-600">
          Paste a YouTube link. The model reads the video's title, description, statistics,
          comments and thumbnail and gives it a slop score. Nothing you check is saved.
        </p>
      </div>

      {!enabled ? (
        <p className="rounded border border-slate-200 bg-white p-4 text-sm text-slate-600">
          Checking a video is not available on this server.
        </p>
      ) : (
        <form
          onSubmit={handleSubmit}
          className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white p-3"
        >
          <label className="sr-only" htmlFor="predict-link">
            YouTube video link
          </label>
          <input
            id="predict-link"
            type="text"
            inputMode="url"
            placeholder="https://www.youtube.com/watch?v=..."
            className="min-w-0 flex-1 rounded border border-slate-300 px-3 py-2 text-sm"
            value={link}
            onChange={(event) => {
              setLink(event.target.value)
              if (data || isError) reset()
            }}
          />
          <button
            type="submit"
            className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            disabled={isPending || link.trim() === ''}
          >
            {isPending ? 'Checking...' : 'Check video'}
          </button>
        </form>
      )}

      {isPending && (
        <p role="status" className="text-sm text-slate-600">
          Reading the video, its comments and its thumbnail. This can take up to a minute,
          especially the first time after the server starts.
        </p>
      )}
      {isError && (
        <p role="alert" className="text-sm text-red-600">
          {errorMessage(error)}
        </p>
      )}
      {data && <PredictionResultCard result={data} />}
    </div>
  )
}
