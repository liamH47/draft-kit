import { useMemo, useState } from 'react'

import type { PoolPlayer, Tag } from '../api/types'
import { PlayerRow } from './PlayerRow'

type Props = {
  players: PoolPlayer[]
  onDraft?: (playerId: string, isMine: boolean | null, name?: string) => void
  onTag?: (playerId: string, tag: Tag | null) => void
  limit?: number
}

// 'value' is the server's order: value over replacement, the same measure the
// recommendation score is built on — it tracks ADP roughly while keeping the
// model's opinion. The others are one click away; nulls sort last.
type SortKey = 'value' | 'points' | 'vorp' | 'adp' | 'consensus_rank'

const SORTS: Record<SortKey, (a: PoolPlayer, b: PoolPlayer) => number> = {
  value: (a, b) => a.rank - b.rank,
  points: (a, b) => b.points - a.points,
  vorp: (a, b) => b.vorp - a.vorp,
  adp: (a, b) => (a.adp ?? Infinity) - (b.adp ?? Infinity),
  consensus_rank: (a, b) => (a.consensus_rank ?? Infinity) - (b.consensus_rank ?? Infinity),
}

export function PlayerTable({ players, onDraft, onTag, limit = 200 }: Props) {
  const [sort, setSort] = useState<SortKey>('value')
  const sorted = useMemo(() => [...players].sort(SORTS[sort]), [players, sort])

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
          <th>Tier</th>
          <th>Player</th>
          <th>Pos</th>
          <th>Tm</th>
          <th>Bye</th>
          {sortable('points', 'Pts')}
          {sortable('vorp', 'VORP', 'Value over replacement player — click to sort')}
          {sortable('adp', 'ADP')}
          <th title="Picks past ADP: + is a steal, − is a reach">Δ</th>
          {sortable(
            'consensus_rank',
            'Cons',
            'Consensus rank across ranking lists (ESPN weighted over expert) — click to sort',
          )}
          {onTag && <th>Tags</th>}
          {onDraft && <th />}
        </tr>
      </thead>
      <tbody>
        {sorted.slice(0, limit).map((p) => (
          <PlayerRow key={p.player_id} player={p} onDraft={onDraft} onTag={onTag} />
        ))}
      </tbody>
    </table>
  )
}
