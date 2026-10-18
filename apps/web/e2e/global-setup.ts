import { clerkSetup } from '@clerk/testing/playwright'

/**
 * Prepares Clerk's official testing support before the browser tests run.
 * Needs CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY (development instance only; Clerk refuses
 * production keys here) plus E2E_CLERK_USER_EMAIL, the dedicated test user. In CI these come
 * from GitHub Actions secrets; values never live in the repo.
 */
export default async function globalSetup(): Promise<void> {
  const missing = ['CLERK_PUBLISHABLE_KEY', 'CLERK_SECRET_KEY', 'E2E_CLERK_USER_EMAIL'].filter(
    (name) => !process.env[name],
  )
  if (missing.length > 0) {
    throw new Error(
      `Browser tests need these GitHub secrets (or local env vars): ${missing.join(', ')}`,
    )
  }
  await clerkSetup()
}
