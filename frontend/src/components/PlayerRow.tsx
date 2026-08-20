import type { PoolPlayer, Tag } from '../api/types'
import { adpLabel, tierColor } from '../lib/format'

const TAGS: { value: Tag; label: string; title: string }[] = [
  { value: 'target', label: 'T', title: 'Target — take him ahead of ADP' },
  { value: 'at_adp', label: 'A', title: 'At ADP — take him around his ADP' },
  { value: 'fade', label: 'F', title: 'Fade — only well past his ADP' },
]

type Props = {
  player: PoolPlayer
  onDraft?: (playerId: string, isMine: boolean) => void
  onTag?: (playerId: string, tag: Tag | null) => void
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
