import type { Recommendation } from '../api/types'

type Props = {
  recommendations: Recommendation[]
  onDraft: (playerId: string, isMine: boolean) => void
}

export function RecommendationPanel({ recommendations, onDraft }: Props) {
  if (recommendations.length === 0) return <p className="muted">Draft complete.</p>
  return (
    <ol className="recs">
      {recommendations.map((r) => (
        <li key={r.player_id}>
          <div className="rec-head">
            <strong>{r.name}</strong>
            <span className="pos">{r.position}</span>
            {r.vona !== null && (
              <span
                className={r.vona >= 12 ? 'wait hot' : 'wait'}
                title={
                  r.vona >= 12
                    ? `Waiting costs about ${r.vona.toFixed(0)} points — the next ${r.position} likely to reach your turn is well behind him`
                    : `${r.position} keeps: someone about as good should still be there at your next pick`
                }
              >
                {r.vona >= 12 ? `wait costs ${r.vona.toFixed(0)}` : 'can wait'}
              </span>
            )}
            <span className="score" title="Composite score">
              {r.score.toFixed(0)}
            </span>
          </div>
          <ul className="reasons">
            {r.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <button type="button" className="mine" onClick={() => onDraft(r.player_id, true)}>
            draft him
          </button>
        </li>
      ))}
    </ol>
  )
}
