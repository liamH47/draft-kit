import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api, type LeagueDraft, type RosterSlots } from '../api/client'
import type { ScoringPreset } from '../api/types'
import { UserChip } from '../components/UserChip'

const SCORING: { value: ScoringPreset; label: string }[] = [
  { value: 'ppr', label: 'PPR' },
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'standard', label: 'Standard' },
]

const PLATFORMS = ['sleeper', 'espn', 'yahoo', 'other']

// Order matters: this is how a league settings page reads.
const ROSTER_FIELDS: { key: keyof RosterSlots; label: string; hint?: string }[] = [
  { key: 'qb', label: 'QB' },
  { key: 'rb', label: 'RB' },
  { key: 'wr', label: 'WR' },
  { key: 'te', label: 'TE' },
  { key: 'flex', label: 'FLEX', hint: 'RB/WR/TE' },
  { key: 'superflex', label: 'SFLEX', hint: 'incl. QB' },
  { key: 'k', label: 'K' },
  { key: 'dst', label: 'DST' },
  { key: 'bench', label: 'Bench' },
]

const DEFAULT_ROSTER: RosterSlots = {
  qb: 1, rb: 2, wr: 2, te: 1, flex: 1, superflex: 0, k: 1, dst: 1, bench: 6,
}

export function SetupWizard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const leagues = useQuery({ queryKey: ['leagues'], queryFn: api.listLeagues })
  const [form, setForm] = useState<LeagueDraft>({
    name: 'My league',
    platform: 'espn',
    num_teams: 12,
    my_slot: 1,
    rounds: 15,
    scoring: 'half_ppr',
    roster: DEFAULT_ROSTER,
    autodraft_count: 0,
  })
  const [showRoster, setShowRoster] = useState(false)

  const [espnLeagueId, setEspnLeagueId] = useState('')
  const importEspn = useMutation({
    mutationFn: () =>
      api.importEspnLeague({
        espn_league_id: espnLeagueId.trim(),
        my_slot: form.my_slot,
        autodraft_count: form.autodraft_count,
      }),
    onSuccess: async (league) => {
      await queryClient.invalidateQueries({ queryKey: ['leagues'] })
      const { session } = await api.createSession(league.id, `${league.name} draft`)
      navigate(`/draft/${session.id}`)
    },
  })

  const create = useMutation({
    mutationFn: () => api.createLeague(form),
    onSuccess: async (league) => {
      await queryClient.invalidateQueries({ queryKey: ['leagues'] })
      const { session } = await api.createSession(league.id, `${league.name} draft`)
      navigate(`/draft/${session.id}`)
    },
  })

  const set = <K extends keyof LeagueDraft>(key: K, value: LeagueDraft[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const setSlot = (key: keyof RosterSlots, value: number) =>
    setForm((f) => ({ ...f, roster: { ...f.roster, [key]: Math.max(0, value) } }))

  // Starting spots drive replacement level, so it is worth showing the user
  // the number the model will actually use.
  const starters =
    form.roster.qb + form.roster.rb + form.roster.wr + form.roster.te +
    form.roster.flex + form.roster.superflex + form.roster.k + form.roster.dst

  return (
    <main className="wrap">
      <h1>draftkit</h1>
      <UserChip />
      <p className="muted">
        Set up a league, then start a draft. New to draft plans? Read the{' '}
        <Link to="/strategies">strategy guide</Link>.
      </p>

      <section className="import">
        <h2>Import an ESPN league</h2>
        <p className="muted">
          Reads the league's real roster slots and scoring, so replacement level is
          right without anyone retyping settings. Private leagues need{' '}
          <code>DRAFTKIT_ESPN_S2</code> and <code>DRAFTKIT_ESPN_SWID</code> in your{' '}
          <code>.env</code> — never paste those anywhere else.
        </p>
        <div className="import-row">
          <input
            value={espnLeagueId}
            placeholder="ESPN league ID (from the URL: ?leagueId=…)"
            onChange={(e) => setEspnLeagueId(e.target.value)}
          />
          <label>
            Your slot
            <input
              type="number"
              min={1}
              value={form.my_slot}
              onChange={(e) => set('my_slot', Number(e.target.value))}
            />
          </label>
          <button
            type="button"
            disabled={!espnLeagueId.trim() || importEspn.isPending}
            onClick={() => importEspn.mutate()}
          >
            {importEspn.isPending ? 'Reading…' : 'Import'}
          </button>
        </div>
        {importEspn.error && (
          <p className="error">{(importEspn.error as Error).message}</p>
        )}
      </section>

      <h2 className="or">or set it up by hand</h2>

      <form
        className="setup"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate()
        }}
      >
        <label>
          League name
          <input value={form.name} onChange={(e) => set('name', e.target.value)} />
        </label>

        <label>
          Platform
          <select value={form.platform} onChange={(e) => set('platform', e.target.value)}>
            {PLATFORMS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>

        <fieldset>
          <legend>Scoring</legend>
          {SCORING.map((s) => (
            <label key={s.value} className="radio">
              <input
                type="radio"
                name="scoring"
                checked={form.scoring === s.value}
                onChange={() => set('scoring', s.value)}
              />
              {s.label}
            </label>
          ))}
        </fieldset>

        <details className="roster-settings" open={showRoster}>
          <summary onClick={(e) => { e.preventDefault(); setShowRoster((v) => !v) }}>
            Roster settings
            <span className="summary-note">
              {starters} starters + {form.roster.bench} bench
            </span>
          </summary>
          <div className="slot-grid">
            {ROSTER_FIELDS.map((field) => (
              <label key={field.key}>
                {field.label}
                {field.hint && <em>{field.hint}</em>}
                <input
                  type="number"
                  min={0}
                  max={12}
                  value={form.roster[field.key]}
                  onChange={(e) => setSlot(field.key, Number(e.target.value))}
                />
              </label>
            ))}
          </div>
          <p className="slot-help">
            These set replacement level. A 3-WR league values receivers very
            differently from a 2-WR league, so it is worth getting right.
          </p>
        </details>

        <div className="row">
          <label>
            Teams
            <input
              type="number"
              min={4}
              max={20}
              value={form.num_teams}
              onChange={(e) => set('num_teams', Number(e.target.value))}
            />
          </label>
          <label>
            Your draft slot
            <input
              type="number"
              min={1}
              max={form.num_teams}
              value={form.my_slot}
              onChange={(e) => set('my_slot', Number(e.target.value))}
            />
          </label>
          <label>
            Rounds
            <input
              type="number"
              min={1}
              max={30}
              value={form.rounds}
              onChange={(e) => set('rounds', Number(e.target.value))}
            />
          </label>
          <label title="Seats that draft off the platform's list rather than by hand">
            Autodrafters
            <input
              type="number"
              min={0}
              max={form.num_teams}
              value={form.autodraft_count}
              onChange={(e) => set('autodraft_count', Number(e.target.value))}
            />
          </label>
        </div>
        <p className="slot-help">
          Autodrafters follow the platform's ranking list, so they never start a
          positional run. Saying how many there are stops the board telling you to
          reach in a room where nobody else will.
        </p>

        <button type="submit" disabled={create.isPending}>
          {create.isPending ? 'Starting…' : 'Start draft'}
        </button>
        {create.error && <p className="error">{(create.error as Error).message}</p>}
      </form>

      {leagues.data && leagues.data.length > 0 && (
        <section>
          <h2>Your leagues</h2>
          <ul className="leagues">
            {leagues.data.map((l) => (
              <li key={l.id}>
                <span>
                  {l.name} — {l.num_teams} teams, slot {l.my_slot}, {l.scoring_preset}
                </span>
                <span className="league-actions">
                  <button
                    type="button"
                    onClick={async () => {
                      const { session } = await api.createSession(l.id, `${l.name} draft`)
                      navigate(`/draft/${session.id}`)
                    }}
                  >
                    draft
                  </button>
                  <Link to={`/cheatsheet/${l.id}`}>cheat sheet</Link>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  )
}
