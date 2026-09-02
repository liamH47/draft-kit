import { useEffect, useState } from 'react'

import { LABEL, ORDER, applyTheme, readTheme, saveTheme, type Theme } from '../lib/theme'

/** Light / dark / follow-the-system, in that cycle. The glyph shows the state
 *  you are IN; the tooltip says what a click will do, because an icon alone
 *  cannot distinguish "currently dark" from "click for dark". */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme)

  useEffect(() => {
    applyTheme(theme)
    saveTheme(theme)
  }, [theme])

  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length]
  const label = `Theme: ${LABEL[theme].text}. Click for ${LABEL[next].text}.`
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme(next)}
      title={label}
      aria-label={label}
    >
      {LABEL[theme].icon}
    </button>
  )
}
