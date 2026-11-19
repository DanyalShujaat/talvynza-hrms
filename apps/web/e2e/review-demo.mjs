// Read-only page sweep of the running fictional demo. Run: node e2e/review-demo.mjs
import { chromium } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const base = process.env.DEMO_URL || 'http://localhost:5180'
const output = resolve('../../.local/demo/review')
mkdirSync(output, { recursive: true })
const browser = await chromium.launch()
const results = []
const routes = {
  admin: ['/', '/employees', '/org-chart', '/departments', '/branches', '/hire', '/offboarding', '/attendance', '/shifts', '/leave', '/payroll', '/expenses', '/loans', '/performance', '/training', '/tasks', '/assets', '/helpdesk', '/notices', '/policies', '/people/members', '/access/roles', '/audit', '/settings/organization', '/reports'],
  employee: ['/me', '/me/profile', '/me/attendance', '/me/leave', '/me/payslips', '/me/expenses', '/me/loans', '/me/tasks', '/me/notices', '/me/performance', '/me/training', '/me/assets', '/me/helpdesk', '/me/security', '/payroll'],
  manager: ['/', '/employees', '/reports', '/leave', '/attendance', '/expenses', '/performance', '/tasks'],
  finance: ['/', '/payroll', '/expenses', '/reports'],
}
try {
  for (const [role, paths] of Object.entries(routes)) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const page = await context.newPage()
    let failures = []
    page.on('pageerror', e => failures.push(e.message))
    page.on('response', r => { if (r.status() >= 400 && r.url().includes('/api/')) failures.push(`${r.status()} ${r.url()}`) })
    await page.goto(base + '/demo')
    await page.getByRole('button', { name: `Enter as ${role === 'admin' ? 'administrator' : role === 'manager' ? 'team manager' : role}` }).click()
    await page.waitForURL(u => u.pathname !== '/demo')
    for (const path of paths) {
      failures = []
      await page.goto(base + path)
      await page.waitForLoadState('networkidle')
      const headings = await page.locator('h1').allTextContents()
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
      const error = await page.getByRole('alert').allTextContents()
      results.push({ role, path, headings, failures: [...failures], error, overflow })
      if (['/', '/me', '/employees', '/payroll', '/me/leave'].includes(path)) await page.screenshot({ path: `${output}/${role}-${path.replaceAll('/', '_') || 'home'}.png`, fullPage: true })
    }
    await context.close()
  }
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } })
    const page = await context.newPage()
    for (const path of ['/welcome', '/demo', '/login']) {
      await page.goto(base + path)
      await page.waitForLoadState('networkidle')
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
      results.push({ role: 'public', width, path, overflow })
      await page.screenshot({ path: `${output}/public-${width}-${path.slice(1)}.png`, fullPage: true })
    }
    if (width === 390) {
      await page.goto(base + '/demo')
      await page.getByRole('button', { name: 'Enter as employee' }).click()
      await page.waitForURL('**/me')
      await page.waitForLoadState('networkidle')
      await page.screenshot({ path: `${output}/employee-mobile.png`, fullPage: true })
      await page.getByRole('button', { name: 'Open navigation' }).click()
      await page.getByRole('dialog').waitFor()
      await page.screenshot({ path: `${output}/employee-mobile-nav.png` })
      await page.keyboard.press('Escape')
      if (await page.getByRole('dialog').count()) throw new Error('Mobile navigation did not close with Escape')
    }
    await context.close()
  }
  writeFileSync(`${output}/results.json`, JSON.stringify(results, null, 2))
  console.log(JSON.stringify(results.filter(r => r.overflow || r.failures?.length || r.error?.length || r.headings?.length === 0), null, 2))
  console.log(`Reviewed ${results.length} pages. Screenshots: ${output}`)
} finally { await browser.close() }
