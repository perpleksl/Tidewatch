import { expect, test } from '@playwright/test'

import { signInAsTestUser } from './helpers'

// Read-only: browser tests never change the shared staging database.

test('PER-13: System Health lists fake_source with a status label', async ({ page }) => {
  await signInAsTestUser(page)
  await page.goto('/system-health')

  await expect(page.getByRole('heading', { level: 1, name: 'System Health' })).toBeVisible()
  const fake = page.getByTestId('source-fake_source')
  await expect(fake).toBeVisible({ timeout: 20_000 })
  await expect(fake.getByTestId('status')).toHaveText(/^(OK|Degraded|Paused — limit reached.*)$/)
})

test('PER-19: System Health has a New listings (last 7 days) section', async ({ page }) => {
  await signInAsTestUser(page)
  await page.goto('/system-health')

  await expect(
    page.getByRole('heading', { level: 2, name: 'New listings (last 7 days)' }),
  ).toBeVisible({ timeout: 20_000 })
})
