/**
 * Clerk publishable key. It identifies the Clerk instance and is safe to ship to the browser.
 * Set CLERK_PUBLISHABLE_KEY per environment (Vercel settings, or .env locally).
 * Vite only exposes it because vite.config.ts lists the `CLERK_PUBLISHABLE_` prefix; the
 * secret key (CLERK_SECRET_KEY) never matches that prefix and never reaches the browser.
 */
export const CLERK_PUBLISHABLE_KEY: string | undefined =
  import.meta.env.CLERK_PUBLISHABLE_KEY || undefined
