export type Tag = 'target' | 'at_adp' | 'fade'
export type ScoringPreset = 'standard' | 'half_ppr' | 'ppr'

export type PoolPlayer = {
  player_id: string
  name: string
  position: string
  team: string | null
  bye: number | null
  points: number
  adp: number | null
  adp_delta: number | null
  adp_stdev: number | null
  tier: number | null
  tier_expert: number | null
  consensus_rank: number | null
  rank: number
  pos_rank: number
  vorp: number
  vols: number
  tag: Tag | null
  note: string | null
}

export type Recommendation = {
  player_id: string
  name: string
  position: string
  score: number
  vorp: number
  reasons: string[]
}

export type League = {
  id: number
  name: string
  platform: string
  num_teams: number
  my_slot: number
  rounds: number
  scoring_preset: ScoringPreset
  config: Record<string, unknown>
}

export type Pick = {
  id: number
  session_id: number
  overall_no: number
  round_no: number
  slot: number
  player_id: string
  is_mine: number | boolean
  source: string
}

export type OnTheClock = { overall_no: number; round_no: number; slot: number }

export type SourceMeta = { fetched_at: string; stale: boolean }

export type DraftedPlayer = PoolPlayer & {
  overall_no: number
  round_no: number
  is_mine: boolean
}

export type Board = {
  session: { id: number; name: string; league_id: number }
  league: League
  available: PoolPlayer[]
  recommendations: Recommendation[]
  my_players: PoolPlayer[]
  drafted: DraftedPlayer[]
  my_counts: Record<string, number>
  picks: Pick[]
  on_the_clock: OnTheClock | null
  picks_until_my_turn: number | null
  picks_made: number
  total_picks: number
  sources: Record<string, SourceMeta>
}
