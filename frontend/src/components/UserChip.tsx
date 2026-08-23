import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'

/** Who is signed in, and the way out. Renders nothing on a local install
 *  (auth off) — the chrome only appears when there is an account to show. */
export function UserChip() {
  const me = useQuery({ queryKey: ['me'], queryFn: api.me })

  if (me.data?.auth !== 'google' || !me.data.user) return null
  const user = me.data.user

  return (
    <div className="user-chip">
      {user.picture && <img src={user.picture} alt="" referrerPolicy="no-referrer" />}
      <span>{user.name || user.email}</span>
      <button
        type="button"
        className="link"
        onClick={() => {
          void api.logout().then(() => location.assign('/login'))
        }}
      >
        sign out
      </button>
    </div>
  )
}
