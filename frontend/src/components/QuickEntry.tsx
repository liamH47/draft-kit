import { useEffect, useRef, useState } from 'react'

import type { PoolPlayer } from '../api/types'
import { searchPlayers } from '../lib/format'

type Props = {
  players: PoolPlayer[]
  onDraft: (playerId: string, isMine: boolean | null, name: string) => void
}

/** The most-used control on draft night: type a few letters, Enter marks the
 *  player taken by someone else, Shift+Enter marks him as your pick. Focus
 *  returns here after every action so you never reach for the mouse. */
export function QuickEntry({ players, onDraft }: Props) {
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const matches = searchPlayers(players, query)

  // "/" refocuses the box from anywhere on the page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement !== inputRef.current) {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Plain Enter sends null so the server decides ownership from whose slot is
  // on the clock — otherwise muscle memory files your own pick as a rival's.
  // Shift+Enter is the explicit override for entering your pick out of turn.
  function commit(player: PoolPlayer | undefined, isMine: boolean | null) {
    if (!player) return
    onDraft(player.player_id, isMine, player.name)
    setQuery('')
    inputRef.current?.focus()
  }

  return (
    <div className="quick-entry">
      <input
        ref={inputRef}
        autoFocus
        value={query}
        placeholder="Type a name — Enter = taken, Shift+Enter = my pick"
        onChange={(e) => {
          setQuery(e.target.value)
          setHighlight(0) // a new query means a new best match
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            commit(matches[highlight], e.shiftKey ? true : null)
          } else if (e.key === 'ArrowDown') {
            e.preventDefault()
            setHighlight((h) => Math.min(h + 1, matches.length - 1))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setHighlight((h) => Math.max(h - 1, 0))
          } else if (e.key === 'Escape') {
            setQuery('')
          }
        }}
      />
      {matches.length > 0 && (
        <ul className="matches">
          {matches.map((p, i) => (
            <li key={p.player_id} className={i === highlight ? 'on' : undefined}>
              <button type="button" onClick={() => commit(p, null)}>
                <span className="who">
                  {p.name} <em>{p.position}{p.pos_rank} · {p.team ?? 'FA'}</em>
                </span>
                <span className="vorp">{p.vorp.toFixed(0)} VORP</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
