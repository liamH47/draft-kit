import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'

import { api } from '../api/client'

/** Your tags live in the app's database and are mirrored to a JSON file
 *  beside it on every change. These controls are the manual path: take a copy
 *  with you, or pull one back after a reinstall. */
export function TagBackup() {
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [note, setNote] = useState<string | null>(null)

  const save = async () => {
    const tags = await api.listTags()
    const blob = new Blob([JSON.stringify(tags, null, 1)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `draftkit-tags-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const load = async (file: File) => {
    try {
      const parsed = JSON.parse(await file.text())
      const { imported } = await api.importTags(parsed)
      setNote(`Loaded ${imported} tag${imported === 1 ? '' : 's'}`)
      queryClient.invalidateQueries()
    } catch (err) {
      setNote(`Could not read that file — ${(err as Error).message}`)
    }
  }

  return (
    <p className="tag-backup">
      <button type="button" onClick={save}>
        save tags to a file
      </button>
      <button type="button" onClick={() => fileInput.current?.click()}>
        load tags from a file
      </button>
      <input
        ref={fileInput}
        type="file"
        accept="application/json,.json"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) void load(file)
          e.target.value = ''
        }}
      />
      {note && <span className="muted">{note}</span>}
    </p>
  )
}
