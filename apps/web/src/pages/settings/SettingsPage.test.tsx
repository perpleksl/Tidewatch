import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { SettingChangeItem, SettingItem } from '@/store/api'
import { makeStore } from '@/store/store'

import { SettingsPage } from './SettingsPage'

vi.mock('@clerk/react', () => import('@/test/clerkMock'))

function item(partial: Partial<SettingItem> & Pick<SettingItem, 'key' | 'value'>): SettingItem {
  return {
    area: 'Data refresh',
    label: partial.key,
    kind: 'integer',
    unit: '',
    valid_range: '1–60',
    prd: '3.3',
    default_value: partial.value,
    is_default: true,
    factors: null,
    ...partial,
  }
}

/** A tiny in-memory stand-in for the settings API, with the same validation messages. */
function fakeApi() {
  const settings: SettingItem[] = [
    item({
      key: 'refresh.launches_minutes',
      label: 'Launches refresh interval',
      value: 5,
      unit: 'minutes',
    }),
    item({
      key: 'scoring.opportunity_weights',
      label: 'Opportunity factor weights',
      area: 'Scoring',
      kind: 'weights',
      valid_range: 'each 0–1, sum 1',
      factors: [
        'valuation_gap',
        'fundamentals_momentum',
        'smart_wallet_accumulation',
        'narrative_fit',
      ],
      value: {
        valuation_gap: '0.25',
        fundamentals_momentum: '0.25',
        smart_wallet_accumulation: '0.25',
        narrative_fit: '0.25',
      },
    }),
    item({
      key: 'ai.tier.professor_deep',
      label: 'Professor (deep dives)',
      area: 'AI models',
      kind: 'ai_tier',
      valid_range: 'Anthropic only',
      value: { provider: 'anthropic', model: 'claude-sonnet-5-5' },
    }),
  ]
  const changes: SettingChangeItem[] = []
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

  const fetchMock = vi.fn(async (req: Request) => {
    const url = new URL(req.url)
    if (url.pathname === '/settings' && req.method === 'GET') return json(settings)
    if (url.pathname === '/settings-changes') return json(changes)
    const match = /^\/settings\/([^/]+)(\/reset)?$/.exec(url.pathname)
    const target = settings.find((s) => s.key === decodeURIComponent(match?.[1] ?? ''))
    if (!target) return json({ detail: 'Unknown setting' }, 404)
    let next: unknown
    let reason = 'edited'
    if (match?.[2]) {
      next = target.default_value
      reason = 'reset to default'
    } else {
      next = ((await req.json()) as { value: unknown }).value
      if (target.kind === 'integer') {
        const n = Number(next)
        if (!Number.isInteger(n) || n < 1 || n > 60)
          return json({ detail: 'Enter a whole number from 1 to 60.' }, 422)
        next = n
      }
      if (target.kind === 'weights') {
        const total = Object.values(next as Record<string, string>).reduce(
          (a, v) => a + Number(v),
          0,
        )
        if (Math.abs(total - 1) > 1e-6)
          return json({ detail: `Weights must add up to 1 (they add up to ${total}).` }, 422)
      }
      if (target.kind === 'ai_tier' && (next as { provider: string }).provider !== 'anthropic')
        return json(
          { detail: 'This tier must use the official Anthropic API (ARCHITECTURE.md AD9).' },
          422,
        )
    }
    changes.unshift({
      key: target.key,
      label: target.label,
      old_value: target.value,
      new_value: next,
      changed_at: '2026-10-18T19:30:00Z',
      reason,
    })
    target.value = next
    target.is_default = JSON.stringify(next) === JSON.stringify(target.default_value)
    return json(target)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { settings, changes, fetchMock }
}

function renderPage() {
  return render(
    <Provider store={makeStore()}>
      <SettingsPage />
    </Provider>,
  )
}

const row = (key: string) => screen.getByTestId(`setting-${key}`)

/** Rows are re-rendered after a save, so always look the row up again while waiting. */
async function expectCurrent(key: string, text: string) {
  await waitFor(() => {
    expect(within(row(key)).getByTestId('current')).toHaveTextContent(text)
  })
}

describe('PER-12 Settings page', () => {
  beforeEach(() => {
    fakeApi()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('AC1: lists every setting with its default value, grouped by area', async () => {
    renderPage()
    expect(
      await screen.findByRole('heading', { level: 2, name: 'Data refresh' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Scoring' })).toBeInTheDocument()
    expect(within(row('refresh.launches_minutes')).getByTestId('default')).toHaveTextContent(
      '5 minutes',
    )
    expect(within(row('scoring.opportunity_weights')).getByTestId('default')).toHaveTextContent(
      'Equal (0.25 each)',
    )
  })

  it('AC2: a saved value is shown as the current value', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = await within(
      await screen.findByTestId('setting-refresh.launches_minutes'),
    ).findByRole('textbox')
    await user.clear(input)
    await user.type(input, '10')
    await user.click(within(row('refresh.launches_minutes')).getByRole('button', { name: 'Save' }))
    await expectCurrent('refresh.launches_minutes', '10 minutes')
  })

  it('AC3 + AC6: "Reset to default" restores the default and the change log shows both changes', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = await within(
      await screen.findByTestId('setting-refresh.launches_minutes'),
    ).findByRole('textbox')
    await user.clear(input)
    await user.type(input, '12')
    await user.click(within(row('refresh.launches_minutes')).getByRole('button', { name: 'Save' }))
    await expectCurrent('refresh.launches_minutes', '12 minutes')
    await user.click(
      within(row('refresh.launches_minutes')).getByRole('button', { name: 'Reset to default' }),
    )
    await expectCurrent('refresh.launches_minutes', '5 minutes')

    const log = await screen.findByTestId('change-log')
    const entries = within(log).getAllByRole('listitem')
    expect(entries).toHaveLength(2)
    expect(entries[0]).toHaveTextContent('reset to default')
    expect(entries[0]).toHaveTextContent('12 minutes → 5 minutes')
    expect(entries[1]).toHaveTextContent('5 minutes → 12 minutes')
    expect(entries[1]).toHaveTextContent('18 Oct 2026, 21:30') // shown in Copenhagen time
  })

  it('AC4: an out-of-range value shows the valid range inline and nothing is saved', async () => {
    const user = userEvent.setup()
    renderPage()
    const r = await screen.findByTestId('setting-refresh.launches_minutes')
    const input = within(r).getByRole('textbox')
    await user.clear(input)
    await user.type(input, '-5')
    await user.click(within(r).getByRole('button', { name: 'Save' }))
    expect(await within(r).findByRole('alert')).toHaveTextContent(
      'Enter a whole number from 1 to 60.',
    )
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(within(r).getByTestId('current')).toHaveTextContent('5 minutes')
    expect(await screen.findByText(/no settings have been changed yet/)).toBeInTheDocument()
  })

  it('AC5: weights that do not add up to 1 are refused inline', async () => {
    const user = userEvent.setup()
    renderPage()
    const r = await screen.findByTestId('setting-scoring.opportunity_weights')
    const narrative = within(r).getByRole('textbox', { name: 'Narrative fit' })
    await user.clear(narrative)
    await user.type(narrative, '0.5')
    expect(within(r).getByText('Total: 1.25 (must be 1)')).toBeInTheDocument()
    await user.click(within(r).getByRole('button', { name: 'Save' }))
    expect(await within(r).findByRole('alert')).toHaveTextContent('Weights must add up to 1')
  })

  it('AC5: a professor tier on a provider other than Anthropic is refused inline', async () => {
    const user = userEvent.setup()
    renderPage()
    const r = await screen.findByTestId('setting-ai.tier.professor_deep')
    await user.selectOptions(within(r).getByRole('combobox', { name: 'Provider' }), 'surplus')
    await user.click(within(r).getByRole('button', { name: 'Save' }))
    expect(await within(r).findByRole('alert')).toHaveTextContent('official Anthropic API')
  })

  it('Save is disabled until something changes, and Reset is disabled at the default', async () => {
    renderPage()
    const r = await screen.findByTestId('setting-refresh.launches_minutes')
    expect(within(r).getByRole('button', { name: 'Save' })).toBeDisabled()
    expect(within(r).getByRole('button', { name: 'Reset to default' })).toBeDisabled()
  })
})
