import { expect, test } from '@playwright/test'

// These tests run signed out against each deployed dashboard. Signed-in behaviour is covered
// by unit tests and verified by the Owner on staging (PER-10 definition of done).

test('PER-10 AC1: a signed-out visitor is redirected to the Clerk sign-in page', async ({
  page,
}) => {
  await page.goto('/')

  await expect(page).toHaveURL(/\/sign-in/, { timeout: 20_000 })
  await expect(page.getByRole('heading', { level: 1, name: 'Tidewatch' })).toHaveCount(0)
})

test('PER-10 AC7: the sign-in page offers no way to create an account', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/sign-in/, { timeout: 20_000 })
  await expect(page.getByRole('textbox').first()).toBeVisible({ timeout: 20_000 })

  await expect(page.getByRole('link', { name: /sign up/i })).toHaveCount(0)
})

test('the sign-in page has no horizontal scrolling at the current viewport', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/sign-in/, { timeout: 20_000 })

  const overflows = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(overflows).toBe(false)
})
