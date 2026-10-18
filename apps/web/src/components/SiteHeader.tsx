import { SignOutButton } from '@clerk/react'

/** Top bar on every page: product name and the "Sign out" action (PER-10 AC3). */
export function SiteHeader() {
  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-3">
        <span className="font-semibold tracking-tight">Tidewatch</span>
        <SignOutButton>
          <button
            type="button"
            className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            Sign out
          </button>
        </SignOutButton>
      </div>
    </header>
  )
}
