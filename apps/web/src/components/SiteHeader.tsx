import { SignOutButton } from '@clerk/react'
import { useEffect, useId, useState } from 'react'
import { NavLink, useLocation } from 'react-router'

import { cn } from '@/lib/utils'
import { PAGES } from '@/pages/pages'

const buttonClass =
  'rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2'

function navLinkClass({ isActive }: { isActive: boolean }) {
  return cn(
    'block rounded-md px-3 py-2 text-sm font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2',
    isActive ? 'bg-muted text-foreground' : 'text-muted-foreground',
  )
}

/**
 * Top bar on every page: product name, navigation and "Sign out" (PER-10 AC3, PER-11).
 * Below the `md` breakpoint the navigation collapses behind a "Menu" button (PER-11 AC4).
 */
export function SiteHeader() {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuId = useId()
  const location = useLocation()

  // Close the phone menu after moving to another page.
  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  const links = PAGES.map((page) => (
    <li key={page.path}>
      <NavLink to={page.path} className={navLinkClass}>
        {page.title}
      </NavLink>
    </li>
  ))

  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
        <span className="font-semibold tracking-tight">Tidewatch</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className={cn(buttonClass, 'md:hidden')}
            aria-expanded={menuOpen}
            aria-controls={menuId}
            onClick={() => {
              setMenuOpen((open) => !open)
            }}
          >
            Menu
          </button>
          <SignOutButton>
            <button type="button" className={buttonClass}>
              Sign out
            </button>
          </SignOutButton>
        </div>
      </div>
      {/* Wide screens: always visible. */}
      <nav aria-label="Main" className="mx-auto hidden max-w-5xl px-2 pb-2 md:block">
        <ul className="flex flex-wrap gap-1">{links}</ul>
      </nav>
      {/* Phones: shown when the Menu button is open. */}
      {menuOpen && (
        <nav id={menuId} aria-label="Main" className="border-t px-2 py-2 md:hidden">
          <ul className="flex flex-col gap-1">{links}</ul>
        </nav>
      )}
    </header>
  )
}
