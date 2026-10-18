import { expect, test } from '@playwright/test'

test('PER-8 AC4: the deployed dashboard renders the Tidewatch page', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveTitle('Tidewatch')
  await expect(page.getByRole('heading', { level: 1, name: 'Tidewatch' })).toBeVisible()
})

test('the deployed dashboard reaches its API', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('status')).toHaveText('API status: OK', { timeout: 20_000 })
})

test('no horizontal scrolling at the current viewport', async ({ page }) => {
  await page.goto('/')

  const overflows = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(overflows).toBe(false)
})
