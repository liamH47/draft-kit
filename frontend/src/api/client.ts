// Every call is a relative /api path: Vite proxies in dev, same origin in prod.
import type { Board, League, Me, RankingImport, RankingList, ScoringPreset, Tag } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!resp.ok) {
    if (resp.status === 401 && !location.pathname.startsWith('/login')) {
      // Signed out (or never signed in) on a hosted install: walk to the
      // login page, and still throw so any in-flight UI shows an error
      // rather than a silent blank.
      location.assign('/login')
    }
    const detail = await resp.json().catch(() => ({}))
    throw new Error(detail.detail ?? `HTTP ${resp.status}`)
  }
  return resp.json() as Promise<T>
}

export type RosterSlots = {
  qb: number
  rb: number
  wr: number
  te: number
  flex: number
  superflex: number
  k: number
  dst: number
  bench: number
}

export type LeagueDraft = {
  name: string
  platform: string
  num_teams: number
  my_slot: number
  rounds: number
  scoring: ScoringPreset
  roster: RosterSlots
  autodraft_count: number
}

export const api = {
  health: () => request<{ status: string; version: string }>('/api/health'),
  me: () => request<Me>('/api/me'),
  logout: () => request<{ ok: boolean }>('/auth/logout', { method: 'POST' }),

  listLeagues: () => request<League[]>('/api/leagues'),
  createLeague: (body: LeagueDraft) =>
    request<League>('/api/leagues', { method: 'POST', body: JSON.stringify(body) }),

  // Read a league's real settings from ESPN rather than retyping them.
  importEspnLeague: (body: {
    espn_league_id: string
    my_slot: number
    autodraft_count: number
  }) =>
    request<League>('/api/leagues/import/espn', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  createSession: (leagueId: number, name: string) =>
    request<{ session: { id: number } }>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ league_id: leagueId, name }),
    }),
  listSessions: () =>
    request<{ id: number; league_id: number; name: string; status: string }[]>('/api/sessions'),

  board: (sessionId: number) => request<Board>(`/api/sessions/${sessionId}/board`),

  // isMine null = let the server decide from whose slot is on the clock.
  draftPlayer: (sessionId: number, playerId: string, isMine: boolean | null) =>
    request<unknown>(`/api/sessions/${sessionId}/picks`, {
      method: 'POST',
      body: JSON.stringify({ player_id: playerId, is_mine: isMine }),
    }),
  correctPick: (sessionId: number, overallNo: number, playerId: string) =>
    request<unknown>(`/api/sessions/${sessionId}/picks/${overallNo}`, {
      method: 'PUT',
      body: JSON.stringify({ player_id: playerId }),
    }),

  undo: (sessionId: number) =>
    request<unknown>(`/api/sessions/${sessionId}/picks/undo`, { method: 'POST' }),

  // Tags are per-user, not per-league: your targets follow you into every
  // draft you run.
  setTag: (playerId: string, tag: Tag | null, note?: string | null) =>
    request<unknown>(`/api/tags/${playerId}`, {
      method: 'PUT',
      body: JSON.stringify({ tag, note: note ?? null }),
    }),
  listTags: () => request<Record<string, { tag: Tag | null; note: string | null }>>('/api/tags'),
  importTags: (tags: Record<string, { tag: Tag | null; note: string | null }>) =>
    request<{ imported: number }>('/api/tags/import', {
      method: 'POST',
      body: JSON.stringify({ tags }),
    }),

  // Ranking lists you bring in yourself: paste a cheat sheet, a spreadsheet
  // column, or a table copied off a page. They join the published lists in the
  // consensus rank, so a source we cannot fetch is still a source you can use.
  listRankings: () => request<{ lists: RankingList[] }>('/api/rankings'),
  importRanking: (name: string, text: string) =>
    request<RankingImport>(`/api/rankings/${encodeURIComponent(name)}`, {
      method: 'PUT',
      body: JSON.stringify({ text }),
    }),
  // How far one of your lists counts against the published ones, without
  // re-pasting it. Moves the consensus column only.
  setRankingWeight: (name: string, weight: number) =>
    request<{ name: string; weight: number; rows: number }>(
      `/api/rankings/${encodeURIComponent(name)}`,
      { method: 'PATCH', body: JSON.stringify({ weight }) },
    ),
  deleteRanking: (name: string) =>
    request<unknown>(`/api/rankings/${encodeURIComponent(name)}`, { method: 'DELETE' }),
}
