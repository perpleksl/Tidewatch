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
    runnable: true,
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

  it('PER-14 AC3: the AI marketplace fallback notice is shown, without a Run now button', async () => {
    stub({
      test_controls: false,
      sources: [
        source({
          source: 'ai_marketplace',
          status: 'degraded',
          runnable: false,
          last_error: 'AI marketplace unavailable — using fallback',
        }),
      ],
    })
    renderPage()
    const row = await screen.findByTestId('source-ai_marketplace')
    expect(within(row).getByText('AI marketplace unavailable — using fallback')).toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: 'Run now' })).not.toBeInTheDocument()
  })

  it('no sources shows "Not available" with a reason', async () => {
    stub({ test_controls: false, sources: [] })
    renderPage()
    expect(await screen.findByText(/no data sources are connected yet/)).toBeInTheDocument()
  })
})

describe('PER-19 New listings (last 7 days)', () => {
  it('AC2: shows each new listing with name, chain, outcome, candidate tab and first-seen time', async () => {
    stub({
      test_controls: false,
      sources: [source({ source: 'coingecko_listings' })],
      new_listings: {
        starting_list_at: '2026-10-19T06:00:00Z',
        items: [
          {
            coingecko_id: 'test-new',
            name: 'Test New',
            symbol: 'tn',
            chains: ['base', 'ethereum'],
            outcome: 'assessed',
            reason: 'In the covered universe; waiting for meme classification and scoring',
            candidate_tab: 'mispriced',
            first_seen_at: '2026-10-20T06:00:00Z',
          },
          {
            coingecko_id: 'test-l1',
            name: 'Test L1',
            symbol: 'tl',
            chains: [],
            outcome: 'outside_universe',
            reason: 'Outside the covered universe',
            candidate_tab: null,
            first_seen_at: '2026-10-20T06:00:00Z',
          },
        ],
      },
    })
    renderPage()
    expect(
      await screen.findByRole('heading', { level: 2, name: 'New listings (last 7 days)' }),
    ).toBeInTheDocument()
    const fresh = await screen.findByTestId('listing-test-new')
    expect(within(fresh).getByText('Test New')).toBeInTheDocument()
    expect(within(fresh).getByTestId('chain')).toHaveTextContent('base, ethereum')
    expect(within(fresh).getByTestId('outcome')).toHaveTextContent('Assessed')
    expect(within(fresh).getByTestId('tab')).toHaveTextContent('Mispriced')
    expect(within(fresh).getByText(/First seen 20 Oct 2026, 08:00/)).toBeInTheDocument()
    const outside = screen.getByTestId('listing-test-l1')
    expect(within(outside).getByTestId('outcome')).toHaveTextContent(
      /^Outside the covered universe$/,
    )
    expect(within(outside).getByTestId('chain')).toHaveTextContent('Not available')
    expect(within(outside).getByTestId('tab')).toHaveTextContent('None')
  })

  it('AC1: after the starting list, an empty week says why instead of an empty section', async () => {
    stub({
      test_controls: false,
      sources: [],
      new_listings: { starting_list_at: '2026-10-19T06:00:00Z', items: [] },
    })
    renderPage()
    expect(
      await screen.findByText(
        /no new listings in the last 7 days \(starting list recorded on 19 Oct 2026/,
      ),
    ).toBeInTheDocument()
  })

  it('explains when discovery has not run yet, or the API is older', async () => {
    stub({ test_controls: false, sources: [], new_listings: { starting_list_at: null, items: [] } })
    renderPage()
    expect(await screen.findByText(/CoinGecko discovery has not run yet/)).toBeInTheDocument()
  })
})
