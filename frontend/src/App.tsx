import { useEffect, useState } from 'react'
import './App.css'

type Health = {
  status: string
  version: string
  snapshots: Record<string, unknown>
}

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<Health>
      })
      .then(setHealth)
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <main className="app">
      <h1>draftkit</h1>
      <p className="tagline">Free fantasy football draft assistant</p>
      {health && <p className="health ok">backend ok · v{health.version}</p>}
      {error && <p className="health err">backend unreachable: {error}</p>}
      {!health && !error && <p className="health">checking backend…</p>}
    </main>
  )
}

export default App
