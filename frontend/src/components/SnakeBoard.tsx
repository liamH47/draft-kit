import type { Board, DraftedPlayer } from '../api/types'

// Round r, slot s -> 1-based overall pick number in a snake draft.
const overallFor = (round: number, slot: number, teams: number) =>
  round % 2 === 1 ? (round - 1) * teams + slot : round * teams - slot + 1

// Cells are tiny; surname alone identifies a player the way a wall board does.
const shortName = (name: string) => {
  const parts = name.split(' ')
  return parts.length > 1 ? parts.slice(1).join(' ') : name
}

export function SnakeBoard({ board }: { board: Board }) {
  const { num_teams: teams, rounds, my_slot: mySlot } = board.league
  const byOverall = new Map<number, DraftedPlayer>()
  for (const p of board.drafted) byOverall.set(p.overall_no, p)
  const current = board.on_the_clock?.overall_no
  const slots = Array.from({ length: teams }, (_, i) => i + 1)
  const roundNos = Array.from({ length: rounds }, (_, i) => i + 1)

  return (
    <div className="snake-scroll">
      <table className="snake">
        <thead>
          <tr>
            <th />
            {slots.map((s) => (
              <th key={s} className={s === mySlot ? 'me' : undefined}>
                {s === mySlot ? 'you' : s}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {roundNos.map((r) => (
            <tr key={r}>
              <th>{r}</th>
              {slots.map((s) => {
                const overall = overallFor(r, s, teams)
                const pick = byOverall.get(overall)
                const classes = [
                  pick ? `p-${(pick.position ?? 'unknown').toLowerCase()}` : 'empty',
                  overall === current ? 'current' : '',
                  pick?.is_mine ? 'mine' : '',
                ]
                  .filter(Boolean)
                  .join(' ')
                const label = pick
                  ? pick.position === 'DEF'
                    ? (pick.team ?? pick.name)
                    : shortName(pick.name)
                  : ''
                return (
                  <td
                    key={s}
                    className={classes}
                    title={pick ? `#${overall} ${pick.name} (${pick.position})` : `#${overall}`}
                  >
                    {label}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
