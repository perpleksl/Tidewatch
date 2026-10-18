import { expect, test } from '@playwright/test'

import { PAGES } from '../src/pages/pages'
import { hasHorizontalScroll, mainNav, signInAsTestUser } from './helpers'

// Signed in as the dedicated Clerk test user. Runs on desktop and at 375px (phone project).

test.beforeEach(async ({ page }) => {
  await signInAsTestUser(page)
})

test('PER-11 AC1: after sign-in the Owner lands on the Mispriced page', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveURL(/\/mispriced$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Mispriced' })).toBeVisible()
})

test('PER-11 AC2 + AC3 + AC4: every navigation item opens its page', async ({ page }) => {
  await page.goto('/mispriced')

  for (const item of PAGES) {
    const nav = await mainNav(page)
    await nav.getByRole('link', { name: item.title }).click()

    await expect(page).toHaveURL(new RegExp(`${item.path}$`))
    await expect(page.getByRole('heading', { level: 1, name: item.title })).toBeVisible()
    await expect(page.getByTestId('coming-in')).toHaveText(
      `Not available yet: coming in ${item.milestone}.`,
    )
    expect(await hasHorizontalScroll(page), `${item.title} scrolls sideways`).toBe(false)
  }
})

test('PER-11 AC4: on a phone the navigation is collapsed behind "Menu"', async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? 0) >= 768, 'phone-width check')
  await page.goto('/mispriced')

  const menu = page.getByRole('button', { name: 'Menu' })
  await expect(menu).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeHidden()
  await menu.click()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
})

test('PER-10 AC4: signed in, the API accepts the session', async ({ page }) => {
  await page.goto('/mispriced')

  await expect(page.getByRole('status', { name: 'API status' })).toHaveText('API status: OK', {
    timeout: 20_000,
  })
  await expect(page.getByRole('status', { name: 'API sign-in' })).toHaveText(
    'API sign-in: OK',
    { timeout: 20_000 },
  )
})
