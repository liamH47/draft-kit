import { useEffect, useRef, useState } from 'react'

import type { PoolPlayer, Tag } from '../api/types'
import { type SearchHit, searchPlayers } from '../lib/format'

type DraftedPlayer = {
  player_id: string
  name: string
  overall_no: number
  is_mine: boolean
}

type Props = {
  players: PoolPlayer[]
  drafted?: DraftedPlayer[]
  onDraft: (playerId: string, isMine: boolean | null, name: string) => void
  onTag?: (playerId: string, tag: Tag) => void
  onCorrect?: (overallNo: number, playerId: string, name: string) => void
}

/** The most-used control on draft night: type a few letters, Enter marks the
 *  player taken by someone else, Shift+Enter marks him as your pick. Focus
 *  returns here after every action so you never reach for the mouse. */
export function QuickEntry({ players, drafted = [], onDraft, onTag, onCorrect }: Props) {
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const matches = searchPlayers(players, query, 8, drafted)

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
  function commit(hit: SearchHit | undefined, isMine: boolean | null) {
    if (!hit) return
    if (hit.gone) {
      // He is already off the board. Entering him again is almost always a
      // correction of an earlier mistake, not a second pick.
      onCorrect?.(hit.gone.overall_no, hit.player.player_id, hit.player.name)
    } else {
      onDraft(hit.player.player_id, isMine, hit.player.name)
    }
    setQuery('')
    inputRef.current?.focus()
  }

  function tagHighlighted(tag: Tag) {
    const hit = matches[highlight]
    if (!hit || hit.gone) return
    onTag?.(hit.player.player_id, tag)
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
          } else if (onTag && matches.length > 0 && (e.ctrlKey || e.metaKey)) {
            // Tag without leaving the box: the opinions worth recording are the
            // ones formed while watching the room, not before it.
            const tag = { t: 'target', a: 'at_adp', f: 'fade' }[e.key.toLowerCase()]
            if (tag) {
              e.preventDefault()
              tagHighlighted(tag as Tag)
            }
          }
        }}
      />
      {query.trim() && matches.length === 0 && (
        <p className="no-matches">
          No player matches “{query.trim()}” — check the spelling, or he may not be
          in the pool.
        </p>
      )}
      {matches.length > 0 && (
        <ul className="matches">
          {matches.map((hit, i) => (
            <li
              key={`${hit.player.player_id}-${hit.gone ? 'gone' : 'open'}`}
              className={[i === highlight ? 'on' : '', hit.gone ? 'gone' : ''].join(' ').trim()}
            >
              <button type="button" onClick={() => commit(hit, null)}>
                <span className="who">
                  {hit.player.name}{' '}
                  <em>
                    {hit.gone
                      ? `already taken at #${hit.gone.overall_no}${hit.gone.is_mine ? ' — yours' : ''}`
                      : `${hit.player.position}${hit.player.pos_rank} · ${hit.player.team ?? 'FA'}`}
                  </em>
                </span>
                <span className="vorp">
                  {hit.gone ? 'fix that pick' : `${hit.player.vorp.toFixed(0)} VORP`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
