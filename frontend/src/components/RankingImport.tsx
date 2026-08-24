import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api } from '../api/client'
import type { RankingImport as ImportResult } from '../api/types'

/** Bring in a ranking list nobody publishes for free: paste a PDF cheat sheet,
 *  a spreadsheet column, or a table copied off a page. It joins the published
 *  lists in the consensus rank the board shows itself against.
 *
 *  The names it could NOT match are shown, always. A list that quietly arrives
 *  fourteen players short is the failure you find out about in round four. */
export function RankingImport() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [text, setText] = useState('')
  const [result, setResult] = useState<ImportResult | null>(null)
  const [open, setOpen] = useState(false)

  const lists = useQuery({ queryKey: ['rankings'], queryFn: api.listRankings })

  const load = useMutation({
    mutationFn: () => api.importRanking(name.trim(), text),
    onSuccess: (res) => {
      setResult(res)
      setText('')
      void queryClient.invalidateQueries()
    },
  })

  const remove = useMutation({
    mutationFn: (listName: string) => api.deleteRanking(listName),
    onSuccess: () => {
      setResult(null)
      void queryClient.invalidateQueries()
    },
  })

  const saved = lists.data?.lists ?? []
  const ready = name.trim().length > 0 && text.trim().length > 0

  return (
    <section className="ranking-import">
      <button type="button" className="disclose" onClick={() => setOpen(!open)}>
        {open ? '▾' : '▸'} my ranking lists{saved.length > 0 && ` (${saved.length})`}
      </button>

      {saved.length > 0 && (
        <ul className="ranking-list">
          {saved.map((list) => (
            <li key={list.list_name}>
              <strong>{list.list_name}</strong>{' '}
              <span className={list.matched < list.total ? 'muted warn' : 'muted'}>
                {list.matched} of {list.total} matched
              </span>
              <button
                type="button"
                className="link"
                onClick={() => remove.mutate(list.list_name)}
                title="Remove this list; it stops feeding the consensus rank"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && (
        <div className="ranking-form">
          <p className="muted">
            Paste any ranking list — a PDF cheat sheet, a spreadsheet column, a table copied off a
            page. Numbers, positions, teams and bye weeks are all optional; the order is what
            counts. Page numbers and header rows are thrown away.
          </p>
          <input
            type="text"
            placeholder="list name (e.g. pff-august)"
            value={name}
            maxLength={40}
            onChange={(e) => setName(e.target.value)}
          />
          <textarea
            rows={8}
            placeholder={"1. Ja'Marr Chase WR CIN\n2. Bijan Robinson RB ATL\n3. Justin Jefferson"}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <p>
            <button type="button" disabled={!ready || load.isPending} onClick={() => load.mutate()}>
              {load.isPending ? 'reading…' : 'import list'}
            </button>
            {load.isError && <span className="warn"> {(load.error as Error).message}</span>}
          </p>

          {result && (
            <div className="ranking-result">
              <p>
                <strong>{result.name}</strong>: matched {result.matched} of {result.total}.
              </p>
              {result.unmatched.length > 0 && (
                <p className="warn">
                  Could not find {result.unmatched.length}:{' '}
                  <span className="muted">{result.unmatched.join(', ')}</span>. They are kept in the
                  list so you can correct the spelling and paste it again.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
