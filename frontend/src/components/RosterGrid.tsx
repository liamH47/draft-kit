import type { Board } from '../api/types'

const SLOT_ORDER = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']

export function RosterGrid({ board }: { board: Board }) {
  const roster = (board.league.config.roster ?? {}) as Record<string, number>
  const slots: Record<string, number> = {
    QB: (roster.qb ?? 0) + (roster.superflex ?? 0),
    RB: roster.rb ?? 0,
    WR: roster.wr ?? 0,
    TE: roster.te ?? 0,
    K: roster.k ?? 0,
    DEF: roster.dst ?? 0,
  }
  return (
    <table className="roster">
      <tbody>
        {SLOT_ORDER.map((pos) => {
          const have = board.my_counts[pos] ?? 0
          const want = slots[pos] ?? 0
          const players = board.my_players.filter((p) => p.position === pos)
          return (
            <tr key={pos} className={have < want ? 'unfilled' : undefined}>
              <th>
                {pos} <span className="count">{have}/{want}</span>
              </th>
              <td>{players.map((p) => p.name).join(', ') || <span className="muted">—</span>}</td>
            </tr>
          )
        })}
        {(roster.flex ?? 0) > 0 && (
          <tr>
            <th>FLEX <span className="count">{roster.flex}</span></th>
            <td className="muted">RB/WR/TE</td>
          </tr>
        )}
      </tbody>
    </table>
  )
}
