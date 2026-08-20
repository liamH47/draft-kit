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
