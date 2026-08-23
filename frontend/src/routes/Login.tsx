import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'

/** The hosted install's front door. A plain anchor, not a fetch: the OAuth
 *  redirect chain has to own the whole tab. Local installs (auth off) are
 *  bounced straight back to the board. */
export function Login() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const me = useQuery({ queryKey: ['me'], queryFn: api.me })

  const signedInOrLocal = me.data && (me.data.auth === 'off' || me.data.user !== null)
  useEffect(() => {
    if (signedInOrLocal) navigate('/', { replace: true })
  }, [signedInOrLocal, navigate])

  return (
    <main className="wrap login">
      <h1>draftkit</h1>
      <p className="muted">A draft board for people who would rather be drafting.</p>
      {params.get('error') === 'denied' ? (
        <p className="warn">
          That Google account isn't on the invite list — ask whoever runs this site to add your
          email, then try again.
        </p>
      ) : (
        <p>Sign in to get to your leagues, tags and cheat sheets.</p>
      )}
      <p>
        <a className="button" href="/auth/google/login">
          Sign in with Google
        </a>
      </p>
    </main>
  )
}
