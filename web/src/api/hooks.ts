import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getChannel } from './channels'
import { createIngest } from './ingest'
import { createLabel, getLabelPool, type LabelPoolParams } from './labels'
import type { IngestRequest, LabelCreateRequest } from './types'
import { getVideoDetail, listVideos, type ListVideosParams, type VideoDetailParams } from './videos'

export function useVideos(params: ListVideosParams) {
  return useQuery({
    queryKey: ['videos', params],
    queryFn: () => listVideos(params),
  })
}

export function useVideoDetail(videoId: string | undefined, params: VideoDetailParams = {}) {
  return useQuery({
    queryKey: ['video', videoId, params],
    queryFn: () => getVideoDetail(videoId as string, params),
    enabled: videoId !== undefined,
  })
}

export function useChannel(channelId: string | undefined) {
  return useQuery({
    queryKey: ['channel', channelId],
    queryFn: () => getChannel(channelId as string),
    enabled: channelId !== undefined,
  })
}

export function useLabelPool(params: LabelPoolParams, enabled = true) {
  return useQuery({
    queryKey: ['labelPool', params],
    queryFn: () => getLabelPool(params),
    enabled,
    // Fetched once per labeling session, like the CLI's own pool - re-fetching is an
    // explicit user action (a page refresh / new session), not automatic background
    // refetching, which would reshuffle the pool mid-session out from under the user.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}

export function useCreateLabel() {
  return useMutation({
    mutationFn: (body: LabelCreateRequest) => createLabel(body),
  })
}

export function useCreateIngest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: IngestRequest) => createIngest(body),
    onSuccess: () => {
      // Ingestion runs as a fire-and-forget background task on the server (Phase 5) -
      // there's no push notification when it finishes, so this just invalidates the
      // video list for whenever the user next looks; it won't reflect new data
      // immediately.
      void queryClient.invalidateQueries({ queryKey: ['videos'] })
    },
  })
}
