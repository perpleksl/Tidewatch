import { NotAvailable } from '@/components/NotAvailable'
import type { PageDef } from './pages'

/** A page that exists in the navigation but has no content yet. */
export function PlaceholderPage({ page }: { page: PageDef }) {
  return (
    <section aria-labelledby="page-title" className="flex flex-col gap-4">
      <h1 id="page-title" className="text-3xl font-semibold tracking-tight">
        {page.title}
      </h1>
      <p className="text-muted-foreground" data-testid="coming-in">
        Not available yet: coming in {page.milestone}.
      </p>
    </section>
  )
}

/** Any address that isn't a page. */
export function NotFoundPage() {
  return (
    <section aria-labelledby="page-title" className="flex flex-col gap-4">
      <h1 id="page-title" className="text-3xl font-semibold tracking-tight">
        Page not found
      </h1>
      <NotAvailable reason="there is no page at this address. Use the navigation above." />
    </section>
  )
}
