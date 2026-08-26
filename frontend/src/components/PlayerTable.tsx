import { useMemo, useState } from 'react'

import type { PoolPlayer, Tag } from '../api/types'
import { PlayerRow } from './PlayerRow'

type Props = {
  players: PoolPlayer[]
  onDraft?: (playerId: string, isMine: boolean | null, name?: string) => void
  onTag?: (playerId: string, tag: Tag | null) => void
  limit?: number
}

// 'value' is the server's order: the same measure the recommendation score
// is built on — it tracks ADP roughly while keeping the model's opinion.
// The others are one click away; nulls sort last.
type SortKey = 'value' | 'vona' | 'adp' | 'consensus_rank'

const SORTS: Record<SortKey, (a: PoolPlayer, b: PoolPlayer) => number> = {
  value: (a, b) => a.rank - b.rank,
  vona: (a, b) => (b.vona ?? -Infinity) - (a.vona ?? -Infinity),
  adp: (a, b) => (a.adp ?? Infinity) - (b.adp ?? Infinity),
  consensus_rank: (a, b) => (a.consensus_rank ?? Infinity) - (b.consensus_rank ?? Infinity),
}

export function PlayerTable({ players, onDraft, onTag, limit = 200 }: Props) {
  const [sort, setSort] = useState<SortKey>('value')
  const sorted = useMemo(() => [...players].sort(SORTS[sort]), [players, sort])
  // A tier border between groups only means something when the rows are one
  // position in tier order — interleaved positions would draw noise.
  const showTierBreaks =
    sort === 'value' && sorted.length > 0 && sorted.every((p) => p.position === sorted[0].position)

  const sortable = (key: SortKey, label: string, title?: string) => (
    <th
      title={title ?? `Sort by ${label}; click again for the default order`}
      className={sort === key ? 'sortable on' : 'sortable'}
      onClick={() => setSort(sort === key ? 'value' : key)}
    >
      {label}
      {sort === key ? ' ▾' : ''}
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
          {onTag && <th>Tags</th>}
          {onDraft && <th />}
        </tr>
      </thead>
      <tbody>
        {sorted.slice(0, limit).map((p, i) => (
          <PlayerRow
            key={p.player_id}
            player={p}
            onDraft={onDraft}
            onTag={onTag}
            tierBreak={
              showTierBreaks && i > 0 && p.tier !== null && p.tier !== sorted[i - 1].tier
            }
          />
        ))}
      </tbody>
    </table>
  )
}
