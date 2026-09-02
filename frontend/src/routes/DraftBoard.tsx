import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Tag } from '../api/types'
import { PlayerTable } from '../components/PlayerTable'
import { PositionFilter } from '../components/PositionFilter'
import { QuickEntry } from '../components/QuickEntry'
import { RecommendationPanel } from '../components/RecommendationPanel'
import { RosterGrid } from '../components/RosterGrid'
import { SnakeBoard } from '../components/SnakeBoard'
import { ThemeToggle } from '../components/ThemeToggle'
import { useBoard, useDraftActions, useSessionEvents } from '../state/useBoard'
import { useMyList } from '../state/useMyList'

export function DraftBoard() {
  const sessionId = Number(useParams().sessionId)
  const navigate = useNavigate()
  const { data: board, isLoading, error } = useBoard(sessionId)
  useSessionEvents(sessionId)
  const myList = useMyList()
  const { draft, correct, undo, tag, notice, clearNotice } = useDraftActions(sessionId)
  const [position, setPosition] = useState('ALL')

  // The pick log stores ids; the pool carries the names.
  const byId = useMemo(() => {
    const map = new Map<string, string>()
    for (const p of board?.drafted ?? []) map.set(p.player_id, p.name)
    return map
  }, [board])

  const filtered = useMemo(() => {
    if (!board) return []
    return position === 'ALL'
      ? board.available
      : board.available.filter((p) => p.position === position)
  }, [board, position])

  if (isLoading) return <main className="wrap"><p>Loading the board…</p></main>
  if (error) return <main className="wrap"><p className="error">{(error as Error).message}</p></main>
  if (!board) return null

  const stale = Object.entries(board.sources).filter(([, meta]) => meta.stale)
  const clock = board.on_the_clock
  const myTurn = board.picks_until_my_turn === 0

  const onDraft = (playerId: string, isMine: boolean | null, name?: string) =>
    draft.mutate({ playerId, isMine, name })
  const onTag = (playerId: string, value: Tag | null) => tag.mutate({ playerId, value })

  return (
    <main className="board">
      <header className="topbar">
        <div className="clock">
          {clock ? (
            <>
              <strong>
                Round {clock.round_no}, pick {clock.slot}
              </strong>
              <span className="overall">#{clock.overall_no} of {board.total_picks}</span>
            </>
          ) : (
            <strong>Draft complete</strong>
          )}
        </div>
        <div className={myTurn ? 'turn now' : 'turn'}>
          {board.picks_until_my_turn === null
            ? 'no picks left'
            : myTurn
              ? "you're on the clock"
              : `${board.picks_until_my_turn} picks until your turn`}
        </div>
        <div className="topbar-actions">
          <button type="button" onClick={() => undo.mutate()} disabled={board.picks_made === 0}>
            undo last pick
          </button>
          <button
            type="button"
            onClick={async () => {
              // The old session is kept, never wiped — a misclick here must
              // not be able to destroy a live draft's pick log.
              if (!window.confirm('Start this draft over with an empty board?')) return
              const { session } = await api.createSession(
                board.league.id,
                `${board.league.name} draft`,
              )
              navigate(`/draft/${session.id}`)
            }}
          >
            restart draft
          </button>
          <Link to={`/cheatsheet/${board.league.id}`}>cheat sheet</Link>
          <Link to="/" title="League settings — change parameters or set up a new league">
            settings
          </Link>
          <ThemeToggle />
        </div>
      </header>

      {notice && (
        <p className={notice.kind === 'error' ? 'notice error' : 'notice ok'} role="status">
          {notice.text}
          <button type="button" className="dismiss" onClick={clearNotice} aria-label="dismiss">
            ×
          </button>
        </p>
      )}

      {stale.length > 0 && (
        <p className="stale-banner">
          Using cached data for {stale.map(([name]) => name).join(', ')} — a source is
          unreachable, so these numbers may be a few hours old.
        </p>
      )}

      <QuickEntry
        players={board.available}
        drafted={board.drafted}
        onDraft={onDraft}
        onTag={(playerId, value) => tag.mutate({ playerId, value })}
        onCorrect={(overallNo, playerId, name) => correct.mutate({ overallNo, playerId, name })}
      />
      <p className="entry-hint">
        Enter records the pick · a pick on your slot is filed as yours automatically ·
        Ctrl+T/A/F tags him · typing someone already taken fixes that pick ·
        Shift+Enter only if you are entering your own pick out of turn
      </p>

      <details className="snake-wrap">
        <summary>
          Draft board
          {clock && (
            <span className="summary-note">
              round {clock.round_no} of {board.league.rounds}
            </span>
          )}
        </summary>
        <SnakeBoard board={board} />
      </details>

      <div className="columns">
        <section className="pool-pane">
          <PositionFilter value={position} onChange={setPosition} />
          <PlayerTable players={filtered} onDraft={onDraft} onTag={onTag} myList={myList} />
        </section>

        <aside className="side-pane">
          <h2>Recent picks</h2>
          <ol className="pick-log">
            {board.picks
              .slice(-6)
              .reverse()
              .map((p) => (
                <li key={p.id} className={p.is_mine ? 'mine' : undefined}>
                  <span className="no">#{p.overall_no}</span>
                  {byId.get(p.player_id) ?? p.player_id}
                  {p.is_mine ? <em> you</em> : null}
                </li>
              ))}
            {board.picks.length === 0 && <li className="muted">no picks yet</li>}
          </ol>

          <h2>Recommended</h2>
          <RecommendationPanel
            recommendations={board.recommendations}
            nextPick={board.my_next_pick}
            onDraft={onDraft}
          />
          <h2>Your roster</h2>
          <RosterGrid board={board} />
        </aside>
      </div>
    </main>
  )
}
