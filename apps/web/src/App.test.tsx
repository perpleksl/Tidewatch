import { fireEvent, render, screen, within } from '@testing-library/react'
import { Provider } from 'react-redux'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { AuthGate } from './auth/AuthGate'
import { SignInNotConfigured } from './auth/SignInNotConfigured'
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

function renderDashboard() {
  return render(
    <AuthGate>
      <Provider store={makeStore()}>
        <App />
      </Provider>
    </AuthGate>,
  )
}

describe('Dashboard', () => {
  beforeEach(() => {
    clerkState.signedIn = true
    clerkState.loaded = true
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('PER-6 AC2: shows a page titled "Tidewatch"', () => {
    stubApi()
    renderDashboard()
    expect(screen.getByRole('heading', { level: 1, name: 'Tidewatch' })).toBeInTheDocument()
  })

  it('shows API status OK when /health answers', async () => {
    stubApi()
    renderDashboard()
    const status = screen.getByRole('status', { name: 'API status' })
    expect(await within(status).findByText('OK')).toBeInTheDocument()
  })

  it('shows "Not reachable" when the API is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('network down'))))
    renderDashboard()
    const status = screen.getByRole('status', { name: 'API status' })
    expect(await within(status).findByText('Not reachable')).toBeInTheDocument()
  })
})

describe('PER-10 sign-in', () => {
  beforeEach(() => {
    clerkState.signedIn = true
    clerkState.loaded = true
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('AC1: a signed-out visitor is sent to the Clerk sign-in page and sees no dashboard', () => {
    clerkState.signedIn = false
    stubApi()
    renderDashboard()
    expect(screen.getByTestId('redirect-to-sign-in')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Tidewatch' })).not.toBeInTheDocument()
  })

  it('AC2: a signed-in visitor lands on the dashboard', () => {
    stubApi()
    renderDashboard()
    expect(screen.queryByTestId('redirect-to-sign-in')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Tidewatch' })).toBeInTheDocument()
  })

  it('AC3: a "Sign out" button is shown and signs out when clicked', () => {
    stubApi()
    renderDashboard()
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(signOut).toHaveBeenCalledOnce()
  })

  it('AC4: the dashboard sends the session token and the API accepts it', async () => {
    const fetchMock = stubApi()
    renderDashboard()
    const check = screen.getByRole('status', { name: 'API sign-in' })
    expect(await within(check).findByText('OK')).toBeInTheDocument()
    const meCall = fetchMock.mock.calls.find(([req]) => new URL(req.url).pathname === '/me')
    expect(meCall?.[0].headers.get('Authorization')).toBe('Bearer test-session-token')
  })

  it('AC7: no sign-up link or page is reachable from the dashboard', () => {
    stubApi()
    renderDashboard()
    expect(screen.queryByText(/sign up|create account|register/i)).not.toBeInTheDocument()
    const links = screen.queryAllByRole('link')
    expect(links.filter((a) => /sign-?up/i.test(a.getAttribute('href') ?? ''))).toEqual([])
  })

  it('shows "Loading…" while Clerk starts, never the dashboard', () => {
    clerkState.loaded = false
    stubApi()
    renderDashboard()
    expect(screen.getByText('Loading…')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Tidewatch' })).not.toBeInTheDocument()
  })

  it('fails closed with a reason when the Clerk key is missing', () => {
    render(<SignInNotConfigured />)
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Not available: sign-in is not configured',
    )
  })
})
