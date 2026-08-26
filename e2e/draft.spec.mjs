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
const firstLead = await page.locator('.recs > li').first().locator('.rec-lead').innerText()
assert.match(firstLead, /pick \d+|keeps/, 'the card must lead with the wait-cost')
const firstFoot = await page.locator('.recs > li').first().locator('.rec-foot').innerText()
assert.match(firstFoot, /value [+-]?\d+ · score \d+/, 'value and score demote to the footer')

await page.waitForSelector('.turn')
assert.match(await page.locator('.turn').innerText(), /6 picks until your turn/)
await page.screenshot({ path: `${SHOTS}/2-board.png`, fullPage: true })

// --- keyboard quick entry ------------------------------------------------
const topName = await page.locator('table.pool tbody tr .name-cell .name').first().innerText()
await page.fill('.quick-entry input', topName.slice(0, 5))
await page.waitForSelector('.matches li')
await page.screenshot({ path: `${SHOTS}/3-quick-entry.png` })
await page.press('.quick-entry input', 'Enter')

// The pool table renders a capped number of rows, so with a big live pool the
// row count never changes — wait for the drafted NAME to leave the board.
const nameGone = (name) =>
  ![...document.querySelectorAll('table.pool tbody tr .name-cell .name')].some((c) =>
    c.textContent.startsWith(name),
  )
await page.waitForFunction(nameGone, topName)
const names = await page.locator('table.pool tbody tr .name-cell .name').allInnerTexts()
assert.ok(!names.some((n) => n.startsWith(topName)), `${topName} should be off the board`)

// --- my pick, via Shift+Enter -------------------------------------------
async function draftTopPlayer(modifier = 'Enter') {
  const name = await page.locator('table.pool tbody tr .name-cell .name').first().innerText()
  await page.fill('.quick-entry input', name.slice(0, 5))
  await page.waitForSelector('.matches li')
  await page.press('.quick-entry input', modifier)
  // Wait for him to actually leave the board rather than guessing at a delay.
  await page.waitForFunction(nameGone, name)
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
// Tag the player the engine already recommends most, so this asserts the
// tag->reason wiring rather than the score maths (promotion from further down
// the board is covered by unit tests). The top TABLE row won't do: at live
// pool scale the highest raw-points player is a QB who is not in the top 5.
const targetName = await page.locator('.recs .rec-head strong').first().innerText()
const targetRow = page
  .locator('table.pool tbody tr')
  .filter({ hasText: targetName })
  .first()
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
// The last pick made was `mine`; undo must put that name back on the board.
await page.click('button:has-text("undo last pick")')
await page.waitForFunction(
  (name) =>
    [...document.querySelectorAll('table.pool tbody tr .name-cell .name')].some((c) =>
      c.textContent.startsWith(name),
    ),
  mine,
)

// --- strategy guide (static reference page; nothing else exercises the route) ---
await page.goto(`${BASE}/strategies`)
await page.waitForSelector('.guide h1')
assert.match(await page.locator('.guide h1').innerText(), /Draft strategies/)
const strategySections = await page.locator('.guide section[id]').count()
assert.ok(strategySections >= 11, `expected the full catalogue, saw ${strategySections} sections`)
await page.screenshot({ path: `${SHOTS}/6-strategies.png` })

assert.deepEqual(errors, [], `console/page errors: ${errors.join(' | ')}`)
console.log('E2E PASSED — pool, recommendations, quick entry, tagging, roster, undo, strategies')
await browser.close()
