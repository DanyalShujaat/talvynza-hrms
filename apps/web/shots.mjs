// Temporary review tool: node shots.mjs <email> <password> <prefix> <path,path,...> [dark] [mobile]
import { chromium } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const [, , email, password, prefix, paths, ...flags] = process.argv
const mobile = flags.includes('mobile')
mkdirSync('shots', { recursive: true })
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 }, colorScheme: flags.includes('dark') ? 'dark' : 'light' })
const page = await ctx.newPage()
const base = 'http://localhost:5173'
if (email !== '-') {
  await page.goto(base + '/login')
  await page.getByLabel('Work email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'))
}
for (const p of paths.split(',')) {
  const [path, click] = p.split('@')
  await page.goto(base + path)
  await page.waitForLoadState('networkidle')
  if (click) { await page.getByText(click, { exact: false }).first().click(); await page.waitForLoadState('networkidle') }
  await page.waitForTimeout(700)
  const name = (path.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '') || 'home') + (click ? '_' + click.replace(/\W+/g, '') : '')
  await page.screenshot({ path: `shots/${prefix}_${name}.png`, fullPage: flags.includes('full') })
}
await browser.close()
