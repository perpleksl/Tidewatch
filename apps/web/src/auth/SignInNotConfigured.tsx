/** Shown instead of the dashboard when the build has no Clerk key: fail closed, say why. */
export function SignInNotConfigured() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-4 px-4 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Tidewatch</h1>
      <p role="alert">
        Not available: sign-in is not configured for this deployment (CLERK_PUBLISHABLE_KEY is
        missing).
      </p>
    </main>
  )
}
