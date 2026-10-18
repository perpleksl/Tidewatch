import { ApiStatus } from '@/components/ApiStatus'
import { SignInCheck } from '@/components/SignInCheck'
import { SiteHeader } from '@/components/SiteHeader'

/** The dashboard itself. Only rendered for signed-in visitors (see AuthGate in main.tsx). */
export function App() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-12">
        <h1 className="text-3xl font-semibold tracking-tight">Tidewatch</h1>
        <p className="text-muted-foreground">
          Crypto research dashboard. Placeholder page: features arrive milestone by milestone.
        </p>
        <ApiStatus />
        <SignInCheck />
      </main>
    </>
  )
}
