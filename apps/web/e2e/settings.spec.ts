import { expect, test } from '@playwright/test'

import { signInAsTestUser } from './helpers'

// Read-only on purpose: previews and staging share the staging database, so browser tests
// must never change real settings. Rejected values are safe to try: nothing is saved.

test.beforeEach(async ({ page }) => {
  await signInAsTestUser(page)
  await page.goto('/settings')
})

test('PER-12 AC1: the Settings page lists settings with their defaults', async ({ page }) => {
  await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible()
  const row = page.getByTestId('setting-refresh.launches_minutes')
  await expect(row).toBeVisible({ timeout: 20_000 })
  await expect(row.getByTestId('default')).toHaveText('5 minutes')
  for (const key of [
    'scoring.risk_weights',
    'mispriced.market_cap_max_usd',
    'code.abandoned_days',
    'ai.tier.professor_synthesis',
    'ai.max_deep_dives_per_day',
  ]) {
    await expect(page.getByTestId(`setting-${key}`)).toBeVisible()
  }
})

test('PER-12 AC4: an out-of-range value is refused inline and not saved', async ({ page }) => {
  const row = page.getByTestId('setting-refresh.launches_minutes')
  const before = await row.getByTestId('current').textContent({ timeout: 20_000 })
  await row.getByRole('textbox').fill('-5')
  await row.getByRole('button', { name: 'Save' }).click()

  await expect(row.getByRole('alert')).toHaveText('Enter a whole number from 1 to 60.')
  await page.reload()
  await expect(
    page.getByTestId('setting-refresh.launches_minutes').getByTestId('current'),
  ).toHaveText(before ?? '', { timeout: 20_000 })
})

test('PER-12 AC5: a professor tier cannot be moved off Anthropic', async ({ page }) => {
  const row = page.getByTestId('setting-ai.tier.professor_deep')
  await row.getByRole('combobox', { name: 'Provider' }).selectOption('surplus', { timeout: 20_000 })
  await row.getByRole('button', { name: 'Save' }).click()

  await expect(row.getByRole('alert')).toContainText('official Anthropic API')
})
