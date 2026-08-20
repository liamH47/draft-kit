import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api, type LeagueDraft } from '../api/client'
import type { ScoringPreset } from '../api/types'

const SCORING: { value: ScoringPreset; label: string }[] = [
  { value: 'ppr', label: 'PPR' },
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'standard', label: 'Standard' },
]

const PLATFORMS = ['sleeper', 'espn', 'yahoo', 'other']

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

  return (
    <main className="wrap">
      <h1>draftkit</h1>
      <p className="muted">Set up a league, then start a draft.</p>

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
        </div>

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
                <Link to={`/cheatsheet/${l.id}`}>cheat sheet</Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  )
}
