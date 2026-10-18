import { render, screen } from '@testing-library/react'
import { Provider } from 'react-redux'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { makeStore } from './store/store'

function renderApp() {
  return render(
    <Provider store={makeStore()}>
      <App />
    </Provider>,
  )
}

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('PER-6 AC2: shows a page titled "Tidewatch"', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    renderApp()

    expect(screen.getByRole('heading', { level: 1, name: 'Tidewatch' })).toBeInTheDocument()
  })

  it('shows API status OK when /health answers', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })),
    )
    renderApp()

    expect(await screen.findByText('OK')).toBeInTheDocument()
  })

  it('shows "Not reachable" when the API is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('network down'))))
    renderApp()

    expect(await screen.findByText('Not reachable')).toBeInTheDocument()
  })
})
