/* eslint-disable react-refresh/only-export-components -- test double, not app code */
/**
 * Stand-in for @clerk/react in unit tests: no network, and the test decides whether the
 * visitor is signed in. End-to-end tests use the real Clerk.
 */
import type { ReactNode } from 'react'
import { vi } from 'vitest'

export const clerkState = { signedIn: true, loaded: true }

export const getToken = vi.fn(async () => (clerkState.signedIn ? 'test-session-token' : null))

export function Show({ when, children }: { when: string; children: ReactNode }) {
  if (!clerkState.loaded) return null
  const visible = when === 'signed-in' ? clerkState.signedIn : !clerkState.signedIn
  return visible ? <>{children}</> : null
}

export function ClerkLoading({ children }: { children: ReactNode }) {
  return clerkState.loaded ? null : <>{children}</>
}

export function RedirectToSignIn() {
  return <div data-testid="redirect-to-sign-in" />
}

export const signOut = vi.fn()

export function SignOutButton({ children }: { children: ReactNode }) {
  return (
    <span onClickCapture={() => signOut()} data-testid="sign-out-wrapper">
      {children}
    </span>
  )
}
