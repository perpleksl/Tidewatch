import { setupClerkTestingToken } from '@clerk/testing/playwright'
import { expect, test } from '@playwright/test'

import { hasHorizontalScroll } from './helpers'

// Signed out.

test.beforeEach(async ({ page }) => {
  await setupClerkTestingToken({ page })
})

test('PER-10 AC1: a signed-out visitor is redirected to the sign-in page', async ({ page }) => {
  await page.goto('/launches')

  await expect(page).toHaveURL(/\/sign-in/, { timeout: 20_000 })
  await expect(page.getByRole('navigation', { name: 'Main' })).toHaveCount(0)
})

test('PER-10 AC7: the sign-in page offers no way to create an account', async ({ page }) => {
  await page.goto('/sign-in')
  await expect(page.getByRole('textbox').first()).toBeVisible({ timeout: 20_000 })

  await expect(page.getByRole('link', { name: /sign up/i })).toHaveCount(0)
})

test('the sign-in page has no horizontal scrolling at the current viewport', async ({ page }) => {
  await page.goto('/sign-in')
  await expect(page.getByRole('textbox').first()).toBeVisible({ timeout: 20_000 })

  expect(await hasHorizontalScroll(page)).toBe(false)
})
