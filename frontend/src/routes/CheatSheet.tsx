import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import { RankingImport } from '../components/RankingImport'
import { ThemeToggle } from '../components/ThemeToggle'
import { TagBackup } from '../components/TagBackup'
import type { PoolPlayer, Tag } from '../api/types'
import { PlayerTable } from '../components/PlayerTable'
import { PositionFilter } from '../components/PositionFilter'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMyList } from '../state/useMyList'

/** Pre-draft prep: mark who you'd reach for and who you'd let slide.
 *  Tags are yours, not a league's — they follow you into every draft. */
export function CheatSheet() {
  const leagueId = Number(useParams().leagueId)
  const queryClient = useQueryClient()
  const [position, setPosition] = useState('ALL')
  const [onlyTagged, setOnlyTagged] = useState(false)
  const myList = useMyList()

  const sessions = useQuery({ queryKey: ['sessions'], queryFn: api.listSessions })
  const sessionId = sessions.data?.find((s) => s.league_id === leagueId)?.id
  const board = useQuery({
    queryKey: ['board', sessionId],
    queryFn: () => api.board(sessionId!),
    enabled: sessionId !== undefined,
  })

  const tag = useMutation({
    mutationFn: ({ playerId, value }: { playerId: string; value: Tag | null }) =>
      api.setTag(playerId, value),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['board', sessionId] }),
  })

  const players: PoolPlayer[] = useMemo(() => {
    const all = board.data ? [...board.data.available, ...board.data.my_players] : []
    const byPosition = position === 'ALL' ? all : all.filter((p) => p.position === position)
    const visible = onlyTagged ? byPosition.filter((p) => p.tag) : byPosition
    return [...visible].sort((a, b) => a.rank - b.rank)
  }, [board.data, position, onlyTagged])

  if (sessions.isLoading || board.isLoading) {
    return <main className="wrap"><p>Loading…</p></main>
  }
  if (sessionId === undefined) {
    return (
      <main className="wrap">
        <p>Start a draft for this league first — the cheat sheet uses its player pool.</p>
        <Link to="/">back to setup</Link>
      </main>
    )
  }

  return (
    <main className="wrap wide">
      <header className="sheet-head">
        <h1>Cheat sheet</h1>
        <Link to="/strategies">strategy guide</Link>
        <Link to={`/draft/${sessionId}`}>go to draft board</Link>
        <ThemeToggle />
      </header>
      <p className="muted">
        <strong>T</strong> target (take ahead of ADP) · <strong>A</strong> at ADP ·{' '}
        <strong>F</strong> fade (only well past ADP). Tags feed straight into the
        recommendations during your draft, and they follow you into every league.
      </p>
      <TagBackup />
      <RankingImport />
      <div className="sheet-controls">
        <PositionFilter value={position} onChange={setPosition} />
        <label className="toggle">
          <input
            type="checkbox"
            checked={onlyTagged}
            onChange={(e) => setOnlyTagged(e.target.checked)}
          />
          only tagged
        </label>
      </div>
      <details className="legend">
        <summary>What the columns mean</summary>
        <dl>
          <div>
            <dt>Value</dt>
            <dd>
              season points above a baseline between a typical starter and the waiver wire at his
              position — the default order.
            </dd>
          </div>
          <div>
            <dt>Wait cost</dt>
            <dd>
              points lost by waiting: him vs the best at his position likely to last to your next
              pick.
            </dd>
          </div>
          <div>
            <dt>ADP ±N</dt>
            <dd>
              average draft position across five markets; green +N = still here N picks past his
              price, red −N = N picks early.
            </dd>
          </div>
          <div>
            <dt>Consensus #N</dt>
            <dd>
              average rank across public ranking lists; ↑/↓ = this board disagrees hard with
              them.
            </dd>
          </div>
          <div>
            <dt>Tier breaks</dt>
            <dd>
              in a single-position view, a border marks where one of Boris Chen's tiers ends —
              the last man above the line beats the first man below it.
            </dd>
          </div>
          <div>
            <dt>Badges</dt>
            <dd>
              VALUE: lasts well past his worth · ▲▼: price moving · HOT/COLD: Sleeper adds and
              drops today · injury always reads first.
            </dd>
          </div>
        </dl>
      </details>
      <PlayerTable
        players={players}
        onTag={(playerId, value) => tag.mutate({ playerId, value })}
        myList={myList}
      />
    </main>
  )
}
