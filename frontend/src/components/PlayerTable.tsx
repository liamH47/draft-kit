import type { PoolPlayer, Tag } from '../api/types'
import { PlayerRow } from './PlayerRow'

type Props = {
  players: PoolPlayer[]
  onDraft?: (playerId: string, isMine: boolean | null, name?: string) => void
  onTag?: (playerId: string, tag: Tag | null) => void
  limit?: number
}

export function PlayerTable({ players, onDraft, onTag, limit = 200 }: Props) {
  return (
    <table className="pool">
      <thead>
        <tr>
          <th>Tier</th>
          <th>Player</th>
          <th>Pos</th>
          <th>Tm</th>
          <th>Bye</th>
          <th>Pts</th>
          <th title="Value over replacement player">VORP</th>
          <th>ADP</th>
          <th title="Picks past ADP: + is a steal, − is a reach">Δ</th>
          <th title="Consensus rank across ranking lists (ESPN weighted over expert). Highlighted when the model strongly disagrees.">
            Cons
          </th>
          {onTag && <th>Tags</th>}
          {onDraft && <th />}
        </tr>
      </thead>
      <tbody>
        {players.slice(0, limit).map((p) => (
          <PlayerRow key={p.player_id} player={p} onDraft={onDraft} onTag={onTag} />
        ))}
      </tbody>
    </table>
  )
}
