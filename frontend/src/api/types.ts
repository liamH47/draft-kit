export type Tag = 'target' | 'at_adp' | 'fade'

// Who is signed in. auth "off" is the local install: a fixed local user and
// no login flow at all.
export type Me = {
  auth: 'off' | 'google'
  user: { user_id: string; email: string; name: string; picture: string } | null
}
export type ScoringPreset = 'standard' | 'half_ppr' | 'ppr'

export type PoolPlayer = {
  player_id: string
  name: string
  position: string
  team: string | null
  bye: number | null
  points: number
  // Average Draft Position, blended across five markets.
  adp: number | null
  // Picks he has lasted PAST his market price right now: + is a bargain,
  // - means taking him here is early. Recomputed on every board read.
  adp_delta: number | null
  adp_stdev: number | null
  // Boris Chen's tier where he covers the position (numbered on his OVERALL
  // board — a position's top tier may not read T1), the per-position
  // projection-gap tier where he doesn't. One field, already resolved.
  tier: number | null
  // Average rank across public ranking lists (ESPN, CBS, Boris Chen, your
  // pasted lists) - #1 is best. Display only; never feeds the score.
  // Each list counts by its weight; your own default to 1, level with ESPN.
  consensus_rank: number | null
  // Where each ranking list puts him, before they are blended. Your own lists
  // are namespaced "custom:<name>" so one called "espn" cannot shadow the feed.
  // This is what the board's own list column reads.
  rank_by_source: Record<string, number>
  // Places between where the room drafts him and where we rate him: positive
  // means he lasts past his worth.
  market_edge: number | null
  // How his price has moved since the oldest snapshot we hold. Negative means
  // the room is taking him earlier than it was.
  adp_shift: number | null
  // How many markets could see both readings. One market moving is noise.
  adp_shift_sources: number | null
  // What waiting costs: how much better he is than the next player at his
  // position likely to survive to your next pick. Only set during a draft.
  vona?: number | null
  // Sleeper's own injury designation, verbatim ("IR", "PUP", "Questionable"),
  // and what is hurt. A projection forecasts what he does IF he plays, so this
  // is the column that stops the board leading with a man who is out.
  injury_status: string | null
  injury_body_part: string | null
  // 1 is the starter. A 2 in front of a high projection is a handcuff.
  depth_chart_order: number | null
  // Net waiver churn on Sleeper over the last day, scaled against the hottest
  // add in football: +100 is the most-added player, negative means the rooms
  // are dropping him. It reacts within hours, where ADP takes days.
  buzz: number | null
  rank: number
  pos_rank: number
  vorp: number
  vols: number
  // Season points above the position's baseline (a VOLS-leaning blend of
  // "typical starter" and "waiver wire") - the number the board orders by.
  value: number
  tag: Tag | null
  note: string | null
}

export type Recommendation = {
  player_id: string
  name: string
  position: string
  score: number
  // The board's value number (the VOLS-leaning blend), NOT true VORP.
  value: number
  vona: number | null
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

/** A ranking list the user pasted in themselves. */
export type RankingList = {
  list_name: string
  total: number
  matched: number
  updated_at: string
  /** How far this list counts inside the consensus rank. 1 is level with
   *  ESPN and CBS; 0 keeps the column and drops the vote. Never touches the
   *  score - a ranking predicts who gets taken, not who is good. */
  weight: number
}

export type RankingImport = {
  name: string
  total: number
  matched: number
  unmatched: string[]
  weight: number
}

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
  /** The pick the wait-cost is measured against: "waiting to pick N costs...". */
  my_next_pick: number | null
  picks_made: number
  total_picks: number
  sources: Record<string, SourceMeta>
}
