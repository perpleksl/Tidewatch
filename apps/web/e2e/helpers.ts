import { setupClerkTestingToken, clerk } from '@clerk/testing/playwright'
import { expect, type Page } from '@playwright/test'

/** Signs the dedicated Clerk test user in, using Clerk's official testing helpers. */
export async function signInAsTestUser(page: Page): Promise<void> {
  const emailAddress = process.env.E2E_CLERK_USER_EMAIL
  if (!emailAddress) throw new Error('E2E_CLERK_USER_EMAIL is not set')
  await setupClerkTestingToken({ page })
  await page.goto('/sign-in')
  await clerk.signIn({ page, emailAddress })
}

/** Opens the navigation: always visible on wide screens, behind "Menu" on phones. */
export async function mainNav(page: Page) {
  const menu = page.getByRole('button', { name: 'Menu' })
  if (await menu.isVisible()) {
    if ((await menu.getAttribute('aria-expanded')) !== 'true') await menu.click()
  }
  const nav = page.getByRole('navigation', { name: 'Main' })
  await expect(nav).toBeVisible()
  return nav
}

export async function hasHorizontalScroll(page: Page): Promise<boolean> {
  return page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
}
