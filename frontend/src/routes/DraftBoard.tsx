import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import type { Tag } from '../api/types'
import { PlayerTable } from '../components/PlayerTable'
import { PositionFilter } from '../components/PositionFilter'
import { QuickEntry } from '../components/QuickEntry'
import { RecommendationPanel } from '../components/RecommendationPanel'
import { RosterGrid } from '../components/RosterGrid'
import { useBoard, useDraftActions, useSessionEvents } from '../state/useBoard'

export function DraftBoard() {
  const sessionId = Number(useParams().sessionId)
  const { data: board, isLoading, error } = useBoard(sessionId)
  useSessionEvents(sessionId)
  const { draft, correct, undo, tag, notice, clearNotice } = useDraftActions(
    sessionId,
    board?.league.id,
  )
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
          <Link to={`/cheatsheet/${board.league.id}`}>cheat sheet</Link>
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
        Enter marks a player taken · Shift+Enter marks your pick · Ctrl+T/A/F tags him ·
        typing someone already taken fixes that pick
      </p>

      <div className="columns">
        <section className="pool-pane">
          <PositionFilter value={position} onChange={setPosition} />
          <PlayerTable players={filtered} onDraft={onDraft} onTag={onTag} />
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
          <RecommendationPanel recommendations={board.recommendations} onDraft={onDraft} />
          <h2>Your roster</h2>
          <RosterGrid board={board} />
        </aside>
      </div>
    </main>
  )
}
