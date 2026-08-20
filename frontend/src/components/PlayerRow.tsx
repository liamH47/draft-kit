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
    : `Consensus rank across ranking lists`
  return (
    <td className={disagree ? 'num consensus-flag' : 'num'} title={title}>
      {cons.toFixed(0)}
      {disagree && (diff > 0 ? ' ↑' : ' ↓')}
    </td>
  )
}

export function PlayerRow({ player, onDraft, onTag }: Props) {
  const adp = adpLabel(player)
  return (
    <tr className={player.tag ? `tag-${player.tag}` : undefined}>
      <td className="tier-cell">
        <span className="tier-band" style={{ background: tierColor(player.tier) }} />
        {player.tier ?? '—'}
      </td>
      <td className="name-cell">
        {player.name}
        {player.note && <span className="note" title={player.note}> ✎</span>}
      </td>
      <td>
        {player.position}
        {player.pos_rank}
      </td>
      <td>{player.team ?? '—'}</td>
      <td className="num">{player.bye ?? '—'}</td>
      <td className="num">{player.points.toFixed(1)}</td>
      <td className="num strong">{player.vorp.toFixed(1)}</td>
      <td className="num">{player.adp?.toFixed(1) ?? '—'}</td>
      <td className={`num badge ${adp.kind}`} title="Picks he has lasted past ADP">
        {adp.text}
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
