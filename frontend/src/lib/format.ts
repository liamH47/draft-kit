import type { PoolPlayer } from '../api/types'

/** Tier colour bands. Tier 1 is hottest; deep tiers fade to grey. */
export function tierColor(tier: number | null): string {
  if (tier === null) return 'var(--tier-none)'
  const palette = [
    'var(--tier-1)',
    'var(--tier-2)',
    'var(--tier-3)',
    'var(--tier-4)',
    'var(--tier-5)',
  ]
  return palette[Math.min(tier, palette.length) - 1]
}

/** Positive delta = he's lasted past his ADP (a steal); negative = a reach. */
export function adpLabel(player: PoolPlayer): { text: string; kind: 'steal' | 'reach' | 'flat' } {
  if (player.adp_delta === null) return { text: '—', kind: 'flat' }
  const rounded = Math.round(player.adp_delta)
  if (rounded >= 6) return { text: `+${rounded}`, kind: 'steal' }
  if (rounded <= -6) return { text: `${rounded}`, kind: 'reach' }
  return { text: rounded > 0 ? `+${rounded}` : `${rounded}`, kind: 'flat' }
}

/** Rank players for the quick-entry box: prefix matches first, then
 *  substring, each by draft value, so typing "jef" lands on Jefferson. */
export function searchPlayers(players: PoolPlayer[], query: string, limit = 8): PoolPlayer[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const prefix: PoolPlayer[] = []
  const contains: PoolPlayer[] = []
  for (const p of players) {
    const name = p.name.toLowerCase()
    if (name.startsWith(q)) prefix.push(p)
    else if (name.includes(q) || name.split(' ').some((part) => part.startsWith(q))) {
      contains.push(p)
    }
  }
  return [...prefix, ...contains].slice(0, limit)
}
