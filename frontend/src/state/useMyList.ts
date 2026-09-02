import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import type { RankingList } from '../api/types'

/** The board's own ranking column, headed XR, reads exactly one source. This
 *  decides which — and it returns a `rank_by_source` KEY, not a list name, so
 *  a published feed and a pasted list are interchangeable here.
 *
 *  A list you pasted wins, because pasting one is a deliberate act and the
 *  weight you gave it says which. Failing that it falls back to the live
 *  FantasyPros ECR feed, which is the same list most pasted cheat sheets are
 *  a screenshot of — and unlike a screenshot it refreshes itself.
 *
 *  Ties among pasted lists break alphabetically so the column never moves
 *  between two reads.
 */
export const FALLBACK_SOURCE = 'fantasypros'

export function myListSource(lists: RankingList[]): string {
  const best = [...lists].sort(
    (a, b) => b.weight - a.weight || a.list_name.localeCompare(b.list_name),
  )[0]
  return best ? `custom:${best.list_name}` : FALLBACK_SOURCE
}

/** The same, wired to the rankings query that the board and the cheat sheet
 *  already invalidate on every import, reweight and delete. */
export function useMyList(): string {
  const lists = useQuery({ queryKey: ['rankings'], queryFn: api.listRankings })
  return myListSource(lists.data?.lists ?? [])
}
