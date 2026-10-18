import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { AuthGate } from './auth/AuthGate'
import { SignInNotConfigured } from './auth/SignInNotConfigured'
import { SignInPage } from './auth/SignInPage'
import { NotAvailable } from './components/NotAvailable'
import { PAGES } from './pages/pages'
import { makeStore } from './store/store'
import { clerkState, signOut } from './test/clerkMock'

vi.mock('@clerk/react', () => import('./test/clerkMock'))

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** Fake API: /health is public, /me needs the bearer token. */
function stubApi() {
  const fetchMock = vi.fn(async (input: Request) => {
    const url = new URL(input.url)
    if (url.pathname === '/health') return jsonResponse({ status: 'ok' })
    if (url.pathname === '/me') {
      return input.headers.get('Authorization') === 'Bearer test-session-token'
        ? jsonResponse({ user_id: 'user_TEST123' })
        : jsonResponse({ detail: 'Sign-in required' }, 401)
    }
    return jsonResponse({}, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function CurrentPath() {
  return <output data-testid="path">{useLocation().pathname}</output>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/sign-in/*" element={<SignInPage />} />
        <Route
          path="*"
          element={
            <AuthGate>
              <Provider store={makeStore()}>
                <App />
              </Provider>
            </AuthGate>
          }
        />
      </Routes>
      <CurrentPath />
    </MemoryRouter>,
  )
}

const currentPath = () => screen.getByTestId('path').textContent

beforeEach(() => {
  clerkState.signedIn = true
  clerkState.loaded = true
  stubApi()
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('PER-11 dashboard shell', () => {
  it('AC1: after sign-in the Owner lands on the Mispriced page', () => {
    renderAt('/')
    expect(currentPath()).toBe('/mispriced')
    expect(screen.getByRole('heading', { level: 1, name: 'Mispriced' })).toBeInTheDocument()
  })

  it.each(PAGES)(
    'AC2 + AC3: "$title" opens at $path with its title (and "coming in" until built)',
    async (page) => {
      const user = userEvent.setup()
      renderAt(page.path === '/mispriced' ? '/settings' : '/mispriced')
      const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]
      if (!nav) throw new Error('navigation missing')
      await user.click(within(nav).getByRole('link', { name: page.title }))

      expect(currentPath()).toBe(page.path)
      expect(screen.getByRole('heading', { level: 1, name: page.title })).toBeInTheDocument()
      if (page.built) {
        expect(screen.queryByTestId('coming-in')).not.toBeInTheDocument()
      } else {
        expect(screen.getByTestId('coming-in')).toHaveTextContent(
          `Not available yet: coming in ${page.milestone}.`,
        )
      }
    },
  )

  it('AC2: there are exactly seven navigation items, in the PRD order', () => {
    renderAt('/mispriced')
    const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]
    if (!nav) throw new Error('navigation missing')
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual([
      'Mispriced',
      'Narratives',
      'Launches',
      'Track Record',
      'Backtest',
      'Settings',
      'System Health',
    ])
  })

  it('AC2: the current page is marked in the navigation', () => {
    renderAt('/launches')
    const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]
    if (!nav) throw new Error('navigation missing')
    expect(within(nav).getByRole('link', { name: 'Launches' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('AC4: on phones the navigation sits behind a "Menu" button that opens and closes', async () => {
    const user = userEvent.setup()
    renderAt('/mispriced')
    const menu = screen.getByRole('button', { name: 'Menu' })
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getAllByRole('navigation', { name: 'Main' })).toHaveLength(1)

    await user.click(menu)
    expect(menu).toHaveAttribute('aria-expanded', 'true')
    const phoneNav = document.getElementById(menu.getAttribute('aria-controls') ?? '')
    expect(phoneNav).not.toBeNull()

    // Choosing a page closes the menu again.
    await user.click(within(phoneNav as HTMLElement).getByRole('link', { name: 'Backtest' }))
    expect(currentPath()).toBe('/backtest')
    expect(menu).toHaveAttribute('aria-expanded', 'false')
  })

  it('AC5: every navigation item can be reached with Tab and opened with Enter', async () => {
    const user = userEvent.setup()
    renderAt('/mispriced')
    for (const page of PAGES) {
      const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]
      if (!nav) throw new Error('navigation missing')
      const link = within(nav).getByRole('link', { name: page.title })
      // Tab from the start of the page until the link has focus.
      ;(document.activeElement as HTMLElement | null)?.blur()
      for (let i = 0; i < 20 && document.activeElement !== link; i++) await user.tab()
      expect(link).toHaveFocus()
      await user.keyboard('{Enter}')
      expect(currentPath()).toBe(page.path)
    }
  })

  it('an unknown address shows "Page not found" with a reason, not an empty page', () => {
    renderAt('/nowhere')
    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByText('Not available')).toBeInTheDocument()
  })

  it('the reusable NotAvailable component always shows its reason', () => {
    render(<NotAvailable reason="DefiLlama did not respond" />)
    expect(screen.getByText(/DefiLlama did not respond/)).toBeInTheDocument()
    expect(screen.getByText('Not available')).toBeInTheDocument()
  })
})

describe('Connection status (footer)', () => {
  it('shows API status OK when /health answers', async () => {
    renderAt('/mispriced')
    const status = screen.getByRole('status', { name: 'API status' })
    expect(await within(status).findByText('OK')).toBeInTheDocument()
  })

  it('shows "Not reachable" when the API is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('network down'))))
    renderAt('/mispriced')
    const status = screen.getByRole('status', { name: 'API status' })
    expect(await within(status).findByText('Not reachable')).toBeInTheDocument()
  })
})

describe('PER-10 sign-in', () => {
  it('AC1: a signed-out visitor is sent to sign-in and sees no dashboard', () => {
    clerkState.signedIn = false
    renderAt('/launches')
    expect(screen.getByTestId('redirect-to-sign-in')).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument()
  })

  it('the /sign-in page shows Clerk\'s sign-in form when signed out', () => {
    clerkState.signedIn = false
    renderAt('/sign-in')
    expect(screen.getByTestId('clerk-sign-in')).toBeInTheDocument()
  })

  it('a signed-in visitor opening /sign-in goes straight to Mispriced', () => {
    renderAt('/sign-in')
    expect(currentPath()).toBe('/mispriced')
  })

  it('AC3: a "Sign out" button is shown and signs out when clicked', async () => {
    const user = userEvent.setup()
    renderAt('/settings')
    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(signOut).toHaveBeenCalledOnce()
  })

  it('AC4: the dashboard sends the session token and the API accepts it', async () => {
    const fetchMock = stubApi()
    renderAt('/mispriced')
    const check = screen.getByRole('status', { name: 'API sign-in' })
    expect(await within(check).findByText('OK')).toBeInTheDocument()
    const meCall = fetchMock.mock.calls.find(([req]) => new URL(req.url).pathname === '/me')
    expect(meCall?.[0].headers.get('Authorization')).toBe('Bearer test-session-token')
  })

  it('AC7: no sign-up link or page is reachable from the dashboard', () => {
    renderAt('/mispriced')
    expect(screen.queryByText(/sign up|create account|register/i)).not.toBeInTheDocument()
    const links = screen.queryAllByRole('link')
    expect(links.filter((a) => /sign-?up/i.test(a.getAttribute('href') ?? ''))).toEqual([])
  })

  it('shows "Loading…" while Clerk starts, never the dashboard', () => {
    clerkState.loaded = false
    renderAt('/mispriced')
    expect(screen.getByText('Loading…')).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument()
  })

  it('fails closed with a reason when the Clerk key is missing', () => {
    render(<SignInNotConfigured />)
    expect(screen.getByRole('alert')).toHaveTextContent('Not available: sign-in is not configured')
  })
})
