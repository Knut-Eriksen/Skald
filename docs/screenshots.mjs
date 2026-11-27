// Drives the real app and saves README screenshots into docs/screenshots/.
// Usage: node docs/screenshots.mjs [baseUrl]   (or SKALD_URL=...; default http://localhost:8000)
// Saves high-quality JPEGs (2x/3x PNGs are 3-5 MB each).
// Needs playwright: resolved from local node_modules, else the global @playwright/cli install.
import { createRequire } from 'node:module'
import { execSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
let pw
try {
  pw = require('playwright')
} catch {
  const root = execSync('npm root -g').toString().trim()
  pw = require(join(root, '@playwright/cli/node_modules/playwright'))
}

const BASE = process.argv[2] || process.env.SKALD_URL || 'http://localhost:8000'
const USERS = ['knuteriksen', 'kolbuand', 'rspuda']
const OUT = join(dirname(fileURLToPath(import.meta.url)), 'screenshots')
mkdirSync(OUT, { recursive: true })

const browser = await pw.chromium.launch({ channel: 'chrome' })
const settle = async (page, ms = 1500) => {
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(ms)
}
const shot = (page, name) => page.screenshot({ path: join(OUT, name), quality: 88 }).then(() => console.log('saved', name))

async function flow(viewport, scale, shots) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: scale })
  const page = await ctx.newPage()
  page.setDefaultTimeout(120_000) // first-run data loading can take a while
  await page.goto(BASE)

  // landing: add the group
  const input = page.getByLabel('Letterboxd username')
  for (const u of USERS) {
    await input.fill(u)
    await input.press('Enter')
  }
  await page.locator('.chip.pending').first().waitFor({ state: 'detached' }).catch(() => {})
  await page.waitForFunction((n) => document.querySelectorAll('.chip:not(.pending)').length >= n, USERS.length)
  await input.blur()
  await page.locator('.backdrops img').first().waitFor()
  await settle(page, 2500) // let the backdrop crossfade in
  if (shots.landing) await shot(page, shots.landing)

  // quiz: mood, then time
  await page.getByRole('button', { name: /Continue with/ }).click()
  await page.getByRole('button', { name: /Thrilling/ }).click()
  await page.getByRole('button', { name: /Mind-bending/ }).click()
  await page.mouse.move(0, 0)
  await settle(page, 1000)
  if (shots.quiz) await shot(page, shots.quiz)
  await page.getByRole('button', { name: /^Next/ }).click()
  await page.getByRole('button', { name: /A regular evening/ }).click() // auto-advances to results

  // results: wait for the hero, its poster and the staggered reveal
  await page.locator('.hero-title').waitFor()
  await page.locator('.matchcard').waitFor()
  await page.waitForFunction(() => [...document.querySelectorAll('.hero img')].every((i) => i.complete))
  await settle(page, 2500)
  if (shots.results) await shot(page, shots.results)
  await ctx.close()
}

try {
  await flow({ width: 1440, height: 900 }, 2, { landing: 'landing.jpg', quiz: 'quiz.jpg', results: 'results.jpg' })
  await flow({ width: 390, height: 844 }, 3, { results: 'results-mobile.jpg' })
} finally {
  await browser.close()
}
