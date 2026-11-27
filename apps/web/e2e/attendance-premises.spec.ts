import { expect, test } from '@playwright/test'

test('manages branch premises and bulk access, then checks punches inside and outside', async ({ page, context }) => {
  test.slow()
  const email = `premises-${Date.now()}@e2e.example.com`
  const password = 'Violet-Harbor-Lantern-42!'
  const api = context.request
  const register = await api.post('/api/v1/auth/register', { data: {
    email, password, full_name: 'Premises Owner', organization_name: 'Premises Test',
    country: 'PK', currency: 'PKR', timezone: 'Asia/Karachi',
  } })
  expect(register.status()).toBe(202)
  expect(await api.post('/api/v1/auth/login', { data: { email, password } })).toBeOK()
  const csrf = (await context.cookies()).find(c => c.name === 'nx_csrf')?.value
  expect(csrf).toBeTruthy()
  const headers = { 'X-CSRF-Token': csrf! }
  const branchResponse = await api.post('/api/v1/branches', { headers, data: { name: 'Main Office' } })
  expect(branchResponse).toBeOK()
  const branch = await branchResponse.json()
  const departmentResponse = await api.post('/api/v1/departments', { headers, data: { name: 'Operations' } })
  expect(departmentResponse).toBeOK()
  const department = await departmentResponse.json()
  const employee = await (await api.get('/api/v1/me/employee')).json()
  expect(await api.patch(`/api/v1/employees/${employee.id}`, { headers, data: {
    branch_id: branch.id, department_id: department.id, bio_id: 'DEVICE-23',
  } })).toBeOK()

  await context.grantPermissions(['geolocation'])
  await context.setGeolocation({ latitude: 35, longitude: 71, accuracy: 5 })
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2GQAAAAASUVORK5CYII=', 'base64'),
  }))
  const go = (path: string) => page.goto(path)

  await go('/branches')
  await page.getByRole('button', { name: 'Actions for Main Office' }).click()
  await page.getByRole('menuitem', { name: 'Manage premises' }).click()
  const map = page.getByLabel('Map for placing branch premises')
  await expect(map).toBeVisible({ timeout: 20_000 })
  await map.click({ position: { x: 150, y: 120 } })
  const resizeHandle = page.locator('[title="Drag to resize the perimeter"]')
  await expect(resizeHandle).toBeVisible()
  const handle = (await resizeHandle.boundingBox())!
  const x = handle.x + handle.width / 2
  const y = handle.y + handle.height / 2
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x + 55, y, { steps: 5 })
  await page.mouse.up()
  await expect(page.getByLabel('Radius in meters')).not.toHaveValue('100')
  await page.getByLabel('Premise name').fill('Main entrance')
  await page.getByLabel('Latitude').fill('34')
  await page.getByLabel('Longitude').fill('71')
  await page.getByLabel('Radius in meters').fill('100')
  await page.getByRole('button', { name: 'Save premise' }).click()
  await expect(page.getByText('Main entrance', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')

  await page.getByRole('button', { name: 'Actions for Main Office' }).click()
  await page.getByRole('menuitem', { name: 'Bulk attendance settings' }).click()
  await expect(page.getByLabel('Branch', { exact: true })).toHaveValue(branch.id)
  await page.getByRole('link', { name: 'Manage branch premises' }).click()
  await expect(page.getByLabel('Map for placing branch premises')).toBeVisible({ timeout: 20_000 })
  await page.goBack()
  await page.getByLabel('Department', { exact: true }).selectOption({ label: 'Operations' })
  await page.getByLabel('Attendance method').selectOption('mobile')
  await page.reload()
  await expect(page.getByLabel('Attendance method')).toHaveValue('mobile')
  await expect(page.getByLabel('Department', { exact: true })).toHaveValue(department.id)
  await expect(page.getByText(/1 matched · 1 enabled/)).toBeVisible()
  await page.getByRole('button', { name: 'Disable attendance' }).click()
  await page.getByRole('button', { name: 'Disable', exact: true }).click()
  await expect(page.getByText(/1 matched · 0 enabled/)).toBeVisible()
  await go('/me')
  await expect(page.getByText('Web and mobile punches are unavailable for your employee record.')).toBeVisible({ timeout: 15_000 })

  await go('/branches')
  await page.locator('aside').getByRole('link', { name: 'Attendance', exact: true }).click()
  await expect(page.getByLabel('Attendance method')).toHaveValue('mobile')
  await expect(page.getByLabel('Department', { exact: true })).toHaveValue(department.id)
  await page.getByRole('button', { name: 'Enable attendance' }).click()
  await page.getByRole('button', { name: 'Enable', exact: true }).click()
  await expect(page.getByText(/1 matched · 1 enabled/)).toBeVisible()
  await go('/me')
  await page.getByRole('button', { name: 'Check in', exact: true }).click()
  await expect(page.getByText('Your location is outside your branch premises')).toBeVisible()
  await context.setGeolocation({ latitude: 34, longitude: 71, accuracy: 5 })
  await page.getByRole('button', { name: 'Check in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Check out', exact: true })).toBeVisible()

  await go('/branches')
  await page.getByRole('button', { name: '1 saved' }).click()
  await page.getByRole('button', { name: 'Remove', exact: true }).click()
  await page.getByRole('button', { name: 'Remove premise', exact: true }).click()
  await expect(page.getByText(/No premises set/)).toBeVisible()
  await context.setGeolocation({ latitude: 35, longitude: 71, accuracy: 5 })
  await go('/me')
  await expect(page.getByText(/Punch from anywhere/)).toBeVisible()
  await page.getByRole('button', { name: 'Check out', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Check in', exact: true })).toBeVisible()

  await go(`/attendance?tab=tools&branch_id=${branch.id}`)
  await expect(page.getByLabel('Device branch')).toHaveValue(branch.id)
  await page.getByLabel('Punch file').setInputFiles({
    name: 'device.csv', mimeType: 'text/csv',
    buffer: Buffer.from('bio_id,timestamp,kind\nDEVICE-23,2026-01-05T09:00:00,in\n'),
  })
  await page.getByRole('button', { name: 'Import punches' }).click()
  await expect(page.getByText('1 punch imported, 0 duplicates ignored')).toBeVisible()
})
