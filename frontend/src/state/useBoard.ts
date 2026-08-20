import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { api } from '../api/client'
import type { Tag } from '../api/types'

export function useBoard(sessionId: number) {
  return useQuery({
    queryKey: ['board', sessionId],
    queryFn: () => api.board(sessionId),
    // The board is cheap to rebuild and correctness beats cleverness during a
    // live draft, so always refetch on invalidation rather than patching cache.
    staleTime: 0,
  })
}

/** Live pick events. Any producer — this tab, another tab, or the Sleeper
 *  poller once it exists — arrives here as a cache invalidation. */
export function useSessionEvents(sessionId: number) {
  const queryClient = useQueryClient()
  useEffect(() => {
    const source = new EventSource(`/api/sessions/${sessionId}/events`)
    const refresh = () => queryClient.invalidateQueries({ queryKey: ['board', sessionId] })
    source.addEventListener('pick_recorded', refresh)
    source.addEventListener('pick_undone', refresh)
    return () => source.close()
  }, [sessionId, queryClient])
}

export type Notice = { kind: 'ok' | 'error'; text: string }

export function useDraftActions(sessionId: number, leagueId: number | undefined) {
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['board', sessionId] })
  // A failed entry that clears the box silently is how the board drifts out of
  // sync with the room, so every action reports what happened.
  const [notice, setNotice] = useState<Notice | null>(null)

  const draft = useMutation({
    mutationFn: ({
      playerId,
      isMine,
    }: {
      playerId: string
      isMine: boolean | null
      name?: string
    }) => api.draftPlayer(sessionId, playerId, isMine),
    onSuccess: (_data, vars) => {
      setNotice({ kind: 'ok', text: `Recorded ${vars.name ?? 'pick'}` })
      invalidate()
    },
    onError: (err: Error, vars) =>
      setNotice({ kind: 'error', text: `${vars.name ?? 'Pick'} NOT recorded — ${err.message}` }),
  })
  const undo = useMutation({
    mutationFn: () => api.undo(sessionId),
    onSuccess: () => {
      setNotice({ kind: 'ok', text: 'Undid the last pick' })
      invalidate()
    },
    onError: (err: Error) => setNotice({ kind: 'error', text: `Undo failed — ${err.message}` }),
  })
  const tag = useMutation({
    mutationFn: ({ playerId, value }: { playerId: string; value: Tag | null }) =>
      api.setTag(leagueId!, playerId, value),
    onSuccess: invalidate,
    onError: (err: Error) => setNotice({ kind: 'error', text: `Tag failed — ${err.message}` }),
  })
  return { draft, undo, tag, notice, clearNotice: () => setNotice(null) }
}
