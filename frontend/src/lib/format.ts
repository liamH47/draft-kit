import type { PoolPlayer } from '../api/types'

/** Positive delta = he's lasted past his ADP (a steal); negative = a reach. */
export function adpLabel(player: PoolPlayer): { text: string; kind: 'steal' | 'reach' | 'flat' } {
  if (player.adp_delta === null) return { text: '—', kind: 'flat' }
  const rounded = Math.round(player.adp_delta)
  if (rounded >= 6) return { text: `+${rounded}`, kind: 'steal' }
  if (rounded <= -6) return { text: `${rounded}`, kind: 'reach' }
  return { text: rounded > 0 ? `+${rounded}` : `${rounded}`, kind: 'flat' }
}

const SUFFIXES = new Set(['jr', 'sr', 'ii', 'iii', 'iv', 'v'])

/** Mirrors the backend's identity/normalize.py. Names arrive spelled six ways
 *  and are heard across a room, so "A.J.", "AJ", "Ja'Marr", "Smith-Njigba" and
 *  "Kenneth Walker III" all have to collapse to the same thing. */
export function normalizeName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[.'’]/g, '')
    .replace(/[^a-z0-9 ]/g, ' ')
    .split(/\s+/)
    .filter((part) => part && !SUFFIXES.has(part))
    .join(' ')
}

export type SearchHit = {
  player: PoolPlayer
  /** Already off the board. Shown greyed rather than hidden: an empty dropdown
   *  is indistinguishable from a typo when you are behind the room. */
  gone?: { overall_no: number; is_mine: boolean }
}

/** Rank candidates for the quick-entry box: whole-name prefix first, then any
 *  word prefix, then substring — so "jef" finds Jefferson, "st brown" finds
 *  Amon-Ra St. Brown, and "cee dee" finds CeeDee Lamb. */
export function searchPlayers(
  players: PoolPlayer[],
  query: string,
  limit = 8,
  drafted: { player_id: string; name: string; overall_no: number; is_mine: boolean }[] = [],
): SearchHit[] {
  const q = normalizeName(query)
  if (!q) return []
  const squashed = q.replace(/ /g, '')

  const rank = (name: string): number => {
    const norm = normalizeName(name)
    if (norm.startsWith(q)) return 0
    if (norm.split(' ').some((part) => part.startsWith(q))) return 1
    if (norm.includes(q)) return 2
    // "ceedee" typed as "cee dee", or the reverse.
    if (norm.replace(/ /g, '').includes(squashed)) return 3
    return -1
  }

  const hits: { hit: SearchHit; score: number; order: number }[] = []
  for (const p of players) {
    const score = rank(p.name)
    if (score >= 0) hits.push({ hit: { player: p }, score, order: p.rank })
  }
  for (const d of drafted) {
    const score = rank(d.name)
    if (score < 0) continue
    const player = players.find((p) => p.player_id === d.player_id)
    hits.push({
      // Drafted players are not in the pool, so carry just enough to render.
      hit: {
        player: player ?? ({ ...d, position: '', team: null, vorp: 0 } as unknown as PoolPlayer),
        gone: { overall_no: d.overall_no, is_mine: d.is_mine },
      },
      score: score + 10, // always below anyone still available
      order: d.overall_no,
    })
  }

  hits.sort((a, b) => a.score - b.score || a.order - b.order)
  return hits.slice(0, limit).map((h) => h.hit)
}

/** How to name the source behind the XR column in a tooltip. The column is
 *  headed XR whatever feeds it, so the tooltip is the only place that says
 *  whether you are reading your own paste or the live FantasyPros feed. */
export function sourceLabel(key: string) {
  return key.startsWith('custom:') ? `your list "${key.slice(7)}"` : 'FantasyPros ECR'
}
