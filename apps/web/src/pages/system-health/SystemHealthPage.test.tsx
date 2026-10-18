import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SourceHealth, SystemHealth } from '@/store/api'
import { makeStore } from '@/store/store'

import { SystemHealthPage } from './SystemHealthPage'

vi.mock('@clerk/react', () => import('@/test/clerkMock'))

function source(partial: Partial<SourceHealth> & Pick<SourceHealth, 'source'>): SourceHealth {
  return {
    status: 'ok',
    last_success_at: null,
    last_attempt_at: null,
    paused_until: null,
    errors_24h: 0,
    last_error: null,
    run_requested: false,
    test_mode: null,
    ...partial,
  }
}

function stub(health: SystemHealth) {
  const calls: Array<{ path: string; body: unknown }> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (req: Request) => {
      const path = new URL(req.url).pathname
      const body: unknown = req.method === 'POST' ? await req.text() : null
      calls.push({ path, body })
      const json = path === '/system-health' ? health : health.sources[0]
      return new Response(JSON.stringify(json), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }),
  )
  return calls
}

function renderPage() {
  render(
    <Provider store={makeStore()}>
      <SystemHealthPage />
    </Provider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('PER-13 System Health', () => {
  it('lists each source with status, last successful fetch and 24-hour error count', async () => {
    stub({
      test_controls: false,
      sources: [
        source({ source: 'fake_source', last_success_at: '2026-10-18T19:00:00Z' }),
        source({
          source: 'fake_b',
          status: 'degraded',
          errors_24h: 3,
          last_error: 'simulated failure',
        }),
      ],
    })
    renderPage()
    const ok = await screen.findByTestId('source-fake_source')
    expect(within(ok).getByTestId('status')).toHaveTextContent('OK')
    expect(within(ok).getByTestId('last-success')).toHaveTextContent('18 Oct 2026, 21:00')
    const bad = screen.getByTestId('source-fake_b')
    expect(within(bad).getByTestId('status')).toHaveTextContent('Degraded')
    expect(within(bad).getByTestId('last-success')).toHaveTextContent('Never')
    expect(within(bad).getByTestId('errors')).toHaveTextContent('3')
    expect(within(bad).getByText('simulated failure')).toBeInTheDocument()
  })

  it('AC3: a paused source shows "Paused — limit reached" with its resume time', async () => {
    stub({
      test_controls: false,
      sources: [
        source({ source: 'fake_source', status: 'paused', paused_until: '2026-10-18T19:10:00Z' }),
      ],
    })
    renderPage()
    expect(await screen.findByTestId('status')).toHaveTextContent(
      'Paused — limit reached (resumes 18 Oct 2026, 21:10)',
    )
  })

  it('test controls appear only when the API allows them, and ask the worker to run', async () => {
    const user = userEvent.setup()
    const calls = stub({ test_controls: true, sources: [source({ source: 'fake_source' })] })
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Make it fail' }))
    await vi.waitFor(() => {
      expect(calls.map((c) => c.path)).toContain('/system-health/fake_source/run')
    })
    const modeCall = calls.find((c) => c.path === '/system-health/fake_source/test-mode')
    expect(modeCall?.body).toBe(JSON.stringify({ mode: 'fail' }))
  })

  it('production: no test controls', async () => {
    stub({ test_controls: false, sources: [source({ source: 'real_source' })] })
    renderPage()
    await screen.findByTestId('source-real_source')
    expect(screen.queryByRole('heading', { name: /Test controls/ })).not.toBeInTheDocument()
  })

  it('no sources shows "Not available" with a reason', async () => {
    stub({ test_controls: false, sources: [] })
    renderPage()
    expect(await screen.findByText(/no data sources are connected yet/)).toBeInTheDocument()
  })
})
