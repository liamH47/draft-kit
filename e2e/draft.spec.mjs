/**
 * End-to-end smoke of the draft flow against the built artifact:
 * set up a league, enter picks by keyboard, watch the board react.
 * Run with: node e2e/draft.spec.mjs  (expects the app on BASE_URL)
 */
import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'

const BASE = process.env.BASE_URL ?? 'http://localhost:8020'
const SHOTS = process.env.SHOT_DIR ?? '/tmp/draftkit-shots'

// The sandbox ships a Chromium build that may not match this Playwright
// release, so prefer the preinstalled binary when it exists.
const executablePath = process.env.CHROMIUM_PATH ?? '/opt/pw-browsers/chromium'
const browser = await chromium.launch(
  existsSync(executablePath) ? { executablePath } : {},
)
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))

// --- setup ---------------------------------------------------------------
await page.goto(BASE)
await page.waitForSelector('form.setup')
await page.fill('.setup input', 'E2E league')
await page.check('input[type=radio] >> nth=0') // PPR
const slot = page.locator('.setup .row input').nth(1)
await slot.fill('7')
await page.screenshot({ path: `${SHOTS}/1-setup.png` })
await page.click('button[type=submit]')

// --- board ---------------------------------------------------------------
await page.waitForURL(/\/draft\/\d+/)
await page.waitForSelector('table.pool tbody tr')
const startingRows = await page.locator('table.pool tbody tr').count()
assert.ok(startingRows > 10, `expected a populated pool, saw ${startingRows}`)

const recs = await page.locator('.recs > li').count()
assert.equal(recs, 5, 'expected five recommendations')
const firstReasons = await page.locator('.recs > li').first().locator('.reasons li').count()
assert.ok(firstReasons > 0, 'recommendations must explain themselves')

await page.waitForSelector('.turn')
assert.match(await page.locator('.turn').innerText(), /6 picks until your turn/)
await page.screenshot({ path: `${SHOTS}/2-board.png`, fullPage: true })

// --- keyboard quick entry ------------------------------------------------
const topName = await page.locator('table.pool tbody tr .name-cell').first().innerText()
await page.fill('.quick-entry input', topName.slice(0, 5))
await page.waitForSelector('.matches li')
await page.screenshot({ path: `${SHOTS}/3-quick-entry.png` })
await page.press('.quick-entry input', 'Enter')

await page.waitForFunction(
  (n) => document.querySelectorAll('table.pool tbody tr').length === n - 1,
  startingRows,
)
const names = await page.locator('table.pool tbody tr .name-cell').allInnerTexts()
assert.ok(!names.some((n) => n.startsWith(topName)), `${topName} should be off the board`)

// --- my pick, via Shift+Enter -------------------------------------------
async function draftTopPlayer(modifier = 'Enter') {
  const before = await page.locator('table.pool tbody tr').count()
  const name = await page.locator('table.pool tbody tr .name-cell').first().innerText()
  await page.fill('.quick-entry input', name.slice(0, 5))
  await page.waitForSelector('.matches li')
  await page.press('.quick-entry input', modifier)
  // Wait for the board to actually shrink rather than guessing at a delay.
  await page.waitForFunction((n) => document.querySelectorAll('table.pool tbody tr').length === n - 1, before)
  return name
}

for (let i = 0; i < 5; i++) await draftTopPlayer()
assert.match(await page.locator('.turn').innerText(), /on the clock/)

const mine = await draftTopPlayer('Shift+Enter')
await page.waitForFunction(
  (name) => document.querySelector('table.roster')?.textContent?.includes(name.split(' ')[0]),
  mine,
)
await page.screenshot({ path: `${SHOTS}/4-my-pick.png`, fullPage: true })

// --- tagging feeds recommendations --------------------------------------
// Tag the top remaining player, who is certain to be in the recommendation
// list, so this asserts the tag->reason wiring rather than the score maths
// (promotion from further down the board is covered by unit tests).
const targetRow = page.locator('table.pool tbody tr').first()
const targetName = await targetRow.locator('.name-cell').innerText()
await targetRow.locator('button.tag').first().click()
await page.waitForFunction(
  () => document.querySelector('.recs')?.textContent?.includes('tagged him a target'),
  null,
  { timeout: 10000 },
)
const recText = await page.locator('.recs').innerText()
assert.ok(recText.includes(targetName.trim()), `${targetName} should still be recommended`)
await page.screenshot({ path: `${SHOTS}/5-tagged.png`, fullPage: true })

// --- searching for someone already taken offers the fix -------------------
// `mine` is a player we drafted earlier, so he is certainly off the board.
const takenSurname = mine.trim().split(/\s+/).pop().slice(0, 4)
await page.fill('.quick-entry input', takenSurname)
await page.waitForSelector('.matches li.gone')
const goneText = await page.locator('.matches li.gone').first().innerText()
assert.ok(/already taken at #\d+/.test(goneText), `expected a "gone" hit, saw: ${goneText}`)
await page.screenshot({ path: `${SHOTS}/6-already-taken.png` })
await page.press('.quick-entry input', 'Escape')

// --- a search that matches nobody says so, rather than going blank ---------
await page.fill('.quick-entry input', 'zzzznobody')
await page.waitForSelector('.no-matches')
await page.press('.quick-entry input', 'Escape')

// --- the pick log records what happened ----------------------------------
const logText = await page.locator('.pick-log').innerText()
assert.ok(/#\d+/.test(logText), 'pick log should show numbered picks')
assert.ok(logText.includes('you'), 'your own pick should be marked in the log')

// --- undo ----------------------------------------------------------------
const beforeUndo = await page.locator('table.pool tbody tr').count()
await page.click('button:has-text("undo last pick")')
await page.waitForFunction(
  (n) => document.querySelectorAll('table.pool tbody tr').length === n + 1,
  beforeUndo,
)

assert.deepEqual(errors, [], `console/page errors: ${errors.join(' | ')}`)
console.log('E2E PASSED — pool, recommendations, quick entry, tagging, roster, undo')
await browser.close()
