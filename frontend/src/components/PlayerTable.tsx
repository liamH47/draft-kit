import { useMemo, useState } from 'react'

import type { PoolPlayer, Tag } from '../api/types'
import { sourceLabel } from '../lib/format'
import { PlayerRow } from './PlayerRow'

type Props = {
  players: PoolPlayer[]
  onDraft?: (playerId: string, isMine: boolean | null, name?: string) => void
  onTag?: (playerId: string, tag: Tag | null) => void
  limit?: number
  /** rank_by_source key for the XR column — a pasted list ("custom:XR") or a
   *  published feed ("fantasypros"). The column hides itself when nothing in
   *  the pool carries that key, so a source that failed to fetch costs a
   *  column rather than showing a screenful of dashes. */
  myList?: string | null
}

// The board opens in XR order — the ranking you actually draft off — and
// falls back to 'value' whenever no XR source is present, which the `active`
// computation below handles without any extra state. 'value' is the server's
// own order: the measure the recommendation score is built on. Note the two
// WILL disagree, and visibly: the Value column and the recommendation panel
// keep using the model whatever the rows are sorted by. That disagreement is
// the useful part — it is where a ranking and the projections part company.
// The others are one click away; nulls sort last.
type SortKey = 'value' | 'vona' | 'adp' | 'consensus_rank' | 'my_list'

const SORTS: Record<Exclude<SortKey, 'my_list'>, (a: PoolPlayer, b: PoolPlayer) => number> = {
  value: (a, b) => a.rank - b.rank,
  vona: (a, b) => (b.vona ?? -Infinity) - (a.vona ?? -Infinity),
  adp: (a, b) => (a.adp ?? Infinity) - (b.adp ?? Infinity),
  consensus_rank: (a, b) => (a.consensus_rank ?? Infinity) - (b.consensus_rank ?? Infinity),
}

/** Sorting by your own list is the whole point of importing one: it turns the
 *  board into that cheat sheet's order with every column of this one beside
 *  it. Players the list never ranked sort last rather than to the top. */
const byMyList = (list: string) => (a: PoolPlayer, b: PoolPlayer) =>
  (a.rank_by_source[list] ?? Infinity) - (b.rank_by_source[list] ?? Infinity)

export function PlayerTable({ players, onDraft, onTag, limit = 200, myList }: Props) {
  const [sort, setSort] = useState<SortKey>('my_list')
  // A source nobody in the pool carries gets no column: the feed may have
  // failed, and a column of dashes reads as "he is unranked" rather than as
  // "this source is missing".
  const column = useMemo(
    () => (myList && players.some((p) => myList in p.rank_by_source) ? myList : null),
    [myList, players],
  )
  // Deleting the list you were sorting by must not leave the board in an
  // order nothing can produce; fall back to the default silently.
  const active: SortKey = sort === 'my_list' && !column ? 'value' : sort
  const sorted = useMemo(
    () =>
      [...players].sort(
        active === 'my_list' ? byMyList(column as string) : SORTS[active],
      ),
    [players, active, column],
  )
  // A tier border between groups only means something when the rows are one
  // position in tier order — interleaved positions would draw noise.
  const showTierBreaks =
    active === 'value' &&
    sorted.length > 0 &&
    sorted.every((p) => p.position === sorted[0].position)

  const sortable = (key: SortKey, label: string, title?: string) => (
    <th
      title={title ?? `Sort by ${label}; click again to go back to Value order`}
      className={active === key ? 'sortable on' : 'sortable'}
      onClick={() => setSort(active === key ? 'value' : key)}
    >
      {label}
      {active === key ? ' ▾' : ''}
    </th>
  )

  return (
    <table className="pool">
      <thead>
        <tr>
          <th>Player</th>
          <th>Pos</th>
          <th>Tm</th>
          <th>Bye</th>
          {sortable(
            'value',
            'Value',
            'Season points above a baseline between a typical starter and the waiver wire at his position — the number this board is ordered by. Click sorts by it.',
          )}
          {sortable(
            'vona',
            'Wait cost',
            'Points lost by waiting: him vs the best at his position likely to last to your next pick. Click sorts by it.',
          )}
          {sortable(
            'adp',
            'ADP',
            'Average Draft Position across five markets. Green +N: still on the board N picks past his usual price. Red −N: taking him now is N picks early. Click sorts by it.',
          )}
          {sortable(
            'consensus_rank',
            'Consensus',
            'Average rank across public ranking lists — #1 is best. ↑/↓ marks where this board disagrees hard: an edge or a data problem, you decide. Click sorts by it.',
          )}
          {/* A fixed label rather than the list's name: "XR" stays the same
              width and the same place on the board whatever the list is
              called, and the header's tooltip says which list is in it. */}
          {column &&
            sortable(
              'my_list',
              'XR',
              `XR — ${sourceLabel(column)}, verbatim, #1 is best. Click sorts the whole board into its order.`,
            )}
          {onTag && <th className="tags-head">Tags</th>}
          {onDraft && <th className="actions-head">Pick</th>}
        </tr>
      </thead>
      <tbody>
        {sorted.slice(0, limit).map((p, i) => (
          <PlayerRow
            key={p.player_id}
            player={p}
            onDraft={onDraft}
            onTag={onTag}
            myList={column}
            tierBreak={
              showTierBreaks && i > 0 && p.tier !== null && p.tier !== sorted[i - 1].tier
            }
          />
        ))}
      </tbody>
    </table>
  )
}
