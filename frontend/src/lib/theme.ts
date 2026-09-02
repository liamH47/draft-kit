/** Light, dark, or whatever the machine says.
 *
 *  Three states rather than a boolean: "system" is the honest default, and a
 *  drafter who has their OS on dark should not have to set this at all. The
 *  choice is stamped on <html> as data-theme, which is what the stylesheet
 *  keys off; absent the attribute, prefers-color-scheme decides.
 *
 *  Persisted per browser. Reading localStorage can THROW outright in a
 *  private window or with site data blocked — not merely return null — so
 *  every access is guarded. Losing the preference is a shrug; a draft board
 *  that will not render because a theme lookup threw is not.
 */
export type Theme = 'light' | 'dark' | 'system'

const KEY = 'draftkit-theme'
export const ORDER: Theme[] = ['system', 'light', 'dark']

export const LABEL: Record<Theme, { icon: string; text: string }> = {
  system: { icon: '◐', text: 'following your system theme' },
  light: { icon: '☀', text: 'light' },
  dark: { icon: '☾', text: 'dark' },
}

export function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch {
    // Storage unavailable. System default is a fine answer.
  }
  return 'system'
}

/** Stamp the choice on the document. "system" removes the attribute rather
 *  than setting it, so the media query is left to answer. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
}

/** Persist the choice. Writing can throw as readily as reading — a private
 *  window, or site data blocked — and the board must not care. */
export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    // A preference that will not persist is a shrug, not a failure.
  }
}
