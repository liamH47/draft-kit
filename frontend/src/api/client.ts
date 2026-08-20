// Every call is a relative /api path: Vite proxies in dev, same origin in prod.
import type { Board, League, ScoringPreset, Tag } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}))
    throw new Error(detail.detail ?? `HTTP ${resp.status}`)
  }
  return resp.json() as Promise<T>
}

export type LeagueDraft = {
  name: string
  platform: string
  num_teams: number
  my_slot: number
  rounds: number
  scoring: ScoringPreset
}

export const api = {
  health: () => request<{ status: string; version: string }>('/api/health'),

  listLeagues: () => request<League[]>('/api/leagues'),
  createLeague: (body: LeagueDraft) =>
    request<League>('/api/leagues', { method: 'POST', body: JSON.stringify(body) }),

  createSession: (leagueId: number, name: string) =>
    request<{ session: { id: number } }>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ league_id: leagueId, name }),
    }),
  listSessions: () =>
    request<{ id: number; league_id: number; name: string; status: string }[]>('/api/sessions'),

  board: (sessionId: number) => request<Board>(`/api/sessions/${sessionId}/board`),

  draftPlayer: (sessionId: number, playerId: string, isMine: boolean) =>
    request<unknown>(`/api/sessions/${sessionId}/picks`, {
      method: 'POST',
      body: JSON.stringify({ player_id: playerId, is_mine: isMine }),
    }),
  undo: (sessionId: number) =>
    request<unknown>(`/api/sessions/${sessionId}/picks/undo`, { method: 'POST' }),

  setTag: (leagueId: number, playerId: string, tag: Tag | null, note?: string | null) =>
    request<unknown>(`/api/leagues/${leagueId}/tags/${playerId}`, {
      method: 'PUT',
      body: JSON.stringify({ tag, note: note ?? null }),
    }),
}
