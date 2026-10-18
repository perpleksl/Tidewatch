import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests against a deployed dashboard (Vercel preview or staging).
 *
 *   E2E_BASE_URL                     URL to test (required in CI; defaults to the local dev server)
 *   VERCEL_AUTOMATION_BYPASS_SECRET  optional; only needed if Vercel Deployment Protection is on
 *   CLERK_PUBLISHABLE_KEY, CLERK_SECRET_KEY, E2E_CLERK_USER_EMAIL
 *                                    sign the dedicated test user in (see e2e/global-setup.ts)
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5173'
const bypassSecret = process.env.VERCEL_AUTOMATION_BYPASS_SECRET

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    ...(bypassSecret
      ? {
          extraHTTPHeaders: {
            'x-vercel-protection-bypass': bypassSecret,
            'x-vercel-set-bypass-cookie': 'true',
          },
        }
      : {}),
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'phone', use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 740 } } },
  ],
})
