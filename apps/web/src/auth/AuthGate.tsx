import { ClerkLoading, RedirectToSignIn, Show } from '@clerk/react'
import type { ReactNode } from 'react'

/**
 * Only signed-in visitors see the dashboard (PRD 3.1). Everyone else is sent to Clerk's
 * prebuilt sign-in page and returns here afterwards.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  return (
    <>
      <ClerkLoading>
        <p className="px-4 py-12 text-center text-sm text-muted-foreground" role="status">
          Loading…
        </p>
      </ClerkLoading>
      <Show when="signed-out">
        <RedirectToSignIn />
      </Show>
      <Show when="signed-in">{children}</Show>
    </>
  )
}
