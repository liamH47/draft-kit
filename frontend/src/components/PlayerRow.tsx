import type { PoolPlayer, Tag } from '../api/types'
import { adpLabel, tierColor } from '../lib/format'

const TAGS: { value: Tag; label: string; title: string }[] = [
  { value: 'target', label: 'T', title: 'Target — take him ahead of ADP' },
  { value: 'at_adp', label: 'A', title: 'At ADP — take him around his ADP' },
  { value: 'fade', label: 'F', title: 'Fade — only well past his ADP' },
]

type Props = {
  player: PoolPlayer
  onDraft?: (playerId: string, isMine: boolean | null, name?: string) => void
  onTag?: (playerId: string, tag: Tag | null) => void
  /** First row of a new tier group (single-position view): draws the border. */
  tierBreak?: boolean
}

// The model disagreeing hard with the room's consensus should be visible,
// not silent — it is either an edge or a data problem, and mid-draft the
// user deserves the chance to decide which.
function ConsensusCell({ player }: { player: PoolPlayer }) {
  const cons = player.consensus_rank
  if (cons === null) return <td className="num muted">—</td>
  const diff = cons - player.rank // + : we are higher on him than consensus
  const disagree = Math.abs(diff) >= 15
  const title = disagree
    ? diff > 0
      ? `Model rank ${player.rank}, consensus ~${cons.toFixed(0)} — the model is much higher on him`
      : `Model rank ${player.rank}, consensus ~${cons.toFixed(0)} — the model is much lower on him`
    : `Average rank across public ranking lists — #1 is best`
  return (
    <td className={disagree ? 'num consensus-flag' : 'num'} title={title}>
      {'#'}
      {cons.toFixed(0)}
      {disagree && (diff > 0 ? ' ↑' : ' ↓')}
    </td>
  )
}

// Sleeper's designations, split the way the score splits them: out for the
// year, versus hurt now and maybe back for week one. Preseason PUP is the
// common case and is a discount, not a write-off.
const SEASON_ENDING = new Set(['IR', 'DNR', 'SUS', 'SUSPENDED'])
const PROVISIONAL = new Set(['PUP', 'NA', 'COV', 'OUT'])

/** The one flag that can cost you a season if it is missing. A projection
 *  forecasts what he does IF he plays; this is whether he will. */
function Injury({ player }: { player: PoolPlayer }) {
  const status = player.injury_status
  if (!status) return null
  const key = status.toUpperCase()
  const hurt = SEASON_ENDING.has(key) ? 'out' : PROVISIONAL.has(key) ? 'doubt' : 'watch'
  const part = player.injury_body_part ? ` (${player.injury_body_part})` : ''
  const gloss =
    hurt === 'out'
      ? 'out for the season'
      : hurt === 'doubt'
        ? 'hurt now, and may not open the season'
        : 'week-to-week; not scored against him'
  // The severe designations are already short. "Questionable" is not, and it
  // is on a hundred players in August — spelled out, it would be the loudest
  // thing on a board where it is the least important.
  const label = hurt === 'watch' ? status[0].toUpperCase() : status.toUpperCase()
  return (
    <span className={`flag injury ${hurt}`} title={`${status}${part} — ${gloss}`}>
      {label}
    </span>
  )
}

/** Two things worth spotting without reading a number: a player the room
 *  lets fall well past what he is worth, and one whose price is moving. */
function Flags({ player }: { player: PoolPlayer }) {
  const edge = player.market_edge ?? 0
  const shift = player.adp_shift ?? 0
  const markets = player.adp_shift_sources ?? 0
  const sleeper = edge >= 20 && (player.adp ?? 0) >= 70
  // One market moving a player is noise. Two or more agreeing is news, so a
  // lone market has to move him further before it is worth your attention.
  const enough = markets >= 2 ? 1.5 : 5
  const rising = shift <= -enough
  const falling = shift >= enough
  const across = `across ${markets} market${markets === 1 ? '' : 's'}`
  // Buzz is relative to the hottest add in football, so a quarter of that is
  // already a lot of rooms moving on one name in a day.
  const buzz = player.buzz ?? 0
  const buzzing = buzz >= 25
  const shunned = buzz <= -25
  return (
    <>
      {sleeper && (
        <span className="flag sleeper" title={`The room takes him ~${edge} picks later than we rate him`}>
          value
        </span>
      )}
      {rising && (
        <span
          className="flag rising"
          title={`Being taken ${Math.abs(shift).toFixed(1)} picks earlier than a few days ago, ${across}`}
        >
          ▲
        </span>
      )}
      {falling && (
        <span
          className="flag falling"
          title={`Slipping ${shift.toFixed(1)} picks down boards since a few days ago, ${across}`}
        >
          ▼
        </span>
      )}
      {buzzing && (
        <span
          className="flag buzz"
          title={`Sleeper rooms are adding him hard today (${buzz} on a scale where 100 is the most-added player in football). Waiver churn moves within hours; ADP takes days.`}
        >
          hot
        </span>
      )}
      {shunned && (
        <span
          className="flag cold"
          title={`Sleeper rooms are dropping him today. Something changed that the ADP has not caught up with.`}
        >
          cold
        </span>
      )}
    </>
  )
}

export function PlayerRow({ player, onDraft, onTag, tierBreak }: Props) {
  const adp = adpLabel(player)
  const rowClass =
    [player.tag ? `tag-${player.tag}` : '', tierBreak ? 'tier-break' : '']
      .filter(Boolean)
      .join(' ') || undefined
  return (
    <tr className={rowClass}>
      <td
        className="tier-cell"
        title={`Tier ${player.tier ?? '—'} — Boris Chen's tiers, numbered on his overall board (projection-gap tiers where he doesn't cover the position). The last man of a tier beats the first man of the next.`}
      >
        <span className="tier-band" style={{ background: tierColor(player.tier) }} />
        {player.tier === null ? '—' : `T${player.tier}`}
      </td>
      <td className="name-cell">
        {/* The name is its own node so the badges beside it can never be read
            as part of it — by a human scanning, or by anything parsing it. */}
        <span className="name">{player.name}</span>
        <Injury player={player} />
        <Flags player={player} />
        {player.note && <span className="note" title={player.note}> ✎</span>}
      </td>
      <td>
        {player.position}
        {player.pos_rank}
      </td>
      <td>{player.team ?? '—'}</td>
      <td className="num">{player.bye ?? '—'}</td>
      <td
        className="num strong"
        title={`vs the waiver wire ${player.vorp.toFixed(0)} · vs a starting player ${player.vols.toFixed(0)}`}
      >
        {player.value.toFixed(0)}
      </td>
      <td
        className={`num ${(player.vona ?? 0) >= 12 ? 'vona-hot' : ''}`}
        title="What waiting costs: points between him and the next player at his position likely to reach your next pick"
      >
        {player.vona === null || player.vona === undefined ? '—' : player.vona.toFixed(0)}
      </td>
      <td className="num adp-cell" title="Picks past his usual price: green + is a bargain, red − is early">
        {player.adp?.toFixed(1) ?? '—'}
        {player.adp_delta !== null && adp.kind !== 'flat' && (
          <span className={`badge ${adp.kind}`}>{adp.text}</span>
        )}
      </td>
      <ConsensusCell player={player} />
      {onTag && (
        <td className="tags">
          {TAGS.map((t) => (
            <button
              key={t.value}
              type="button"
              title={t.title}
              className={player.tag === t.value ? 'tag on' : 'tag'}
              onClick={() => onTag(player.player_id, player.tag === t.value ? null : t.value)}
            >
              {t.label}
            </button>
          ))}
        </td>
      )}
      {onDraft && (
        <td className="actions">
          <button type="button" onClick={() => onDraft(player.player_id, false)}>
            taken
          </button>
          <button type="button" className="mine" onClick={() => onDraft(player.player_id, true)}>
            mine
          </button>
        </td>
      )}
    </tr>
  )
}
