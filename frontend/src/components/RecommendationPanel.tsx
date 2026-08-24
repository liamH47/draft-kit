import type { Recommendation } from '../api/types'

type Props = {
  recommendations: Recommendation[]
  /** The pick the wait-cost is measured against; null in the final round. */
  nextPick: number | null
  onDraft: (playerId: string, isMine: boolean) => void
}

/** The card leads with the number that changes decisions: what waiting until
 *  your next pick costs. Raw value cannot tell Gibbs from Bijan (+199 vs
 *  +187 over a season); the drop-off behind each of them can. */
export function RecommendationPanel({ recommendations, nextPick, onDraft }: Props) {
  if (recommendations.length === 0) return <p className="muted">Draft complete.</p>
  const horizon = nextPick === null ? 'your next pick' : `pick ${nextPick}`
  return (
    <ol className="recs">
      {recommendations.map((r) => (
        <li key={r.player_id}>
          <div className="rec-head">
            <strong>{r.name}</strong>
            <span className="pos">{r.position}</span>
            <button type="button" className="mine" onClick={() => onDraft(r.player_id, true)}>
              draft him
            </button>
          </div>
          {r.vona !== null && (
            <p className={r.vona >= 12 ? 'rec-lead hot' : 'rec-lead muted'}>
              {r.vona >= 12
                ? `Waiting to ${horizon} costs ~${r.vona.toFixed(0)} pts — the next ${r.position} likely to last that long is far behind him`
                : `${r.position} keeps — someone about as good should still be there at ${horizon}`}
            </p>
          )}
          {r.reasons.length > 0 && (
            <ul className="reasons">
              {r.reasons.slice(0, 3).map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
          <p
            className="rec-foot muted"
            title="value: season points above the position's baseline — the board's own ordering number. score: the sum of every part of the case above, in points."
          >
            value {r.value >= 0 ? '+' : ''}
            {r.value.toFixed(0)} · score {r.score.toFixed(0)}
          </p>
        </li>
      ))}
    </ol>
  )
}
