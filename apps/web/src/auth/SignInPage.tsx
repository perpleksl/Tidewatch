import { Show, SignIn } from '@clerk/react'
import { Navigate } from 'react-router'

import { HOME_PATH } from '@/pages/pages'

/**
 * Clerk's prebuilt sign-in form, unchanged, on the dashboard's own /sign-in address
 * (PER-10). Hosting it here keeps visitors on the dashboard's domain and gives automated
 * tests a public page that loads Clerk (PER-11 AC6).
 */
export function SignInPage() {
  return (
    <main className="flex min-h-screen items-start justify-center px-4 py-12">
      <Show when="signed-out">
        <SignIn routing="path" path="/sign-in" fallbackRedirectUrl={HOME_PATH} />
      </Show>
      <Show when="signed-in">
        <Navigate to={HOME_PATH} replace />
      </Show>
    </main>
  )
}
