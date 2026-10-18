import { NotAvailable } from '@/components/NotAvailable'
import { cn } from '@/lib/utils'
import {
  useGetSystemHealthQuery,
  useRunSourceNowMutation,
  useSetFakeModeMutation,
  type FakeMode,
  type SourceHealth,
} from '@/store/api'

import { formatTime } from '@/pages/settings/format'

import { NewListings } from './NewListings'
import { statusLabel } from './status'

/** Refresh while the page is open, so status changes appear without reloading. */
const POLL_MS = 10_000

const buttonClass =
  'rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50'

const statusColour: Record<SourceHealth['status'], string> = {
  ok: 'border-green-700 text-green-800',
  degraded: 'border-red-700 text-red-800',
  paused: 'border-amber-700 text-amber-800',
}

function SourceRow({ source }: { source: SourceHealth }) {
  const [runNow, { isLoading }] = useRunSourceNowMutation()
  return (
    <li className="flex flex-col gap-2 px-4 py-4" data-testid={`source-${source.source}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{source.source}</span>
        <span
          data-testid="status"
          className={cn(
            'rounded-full border px-2 py-0.5 text-sm font-medium',
            statusColour[source.status],
          )}
        >
          {statusLabel(source)}
        </span>
      </div>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Last successful fetch</dt>
        <dd data-testid="last-success">
          {source.last_success_at ? formatTime(source.last_success_at) : 'Never'}
        </dd>
        <dt className="text-muted-foreground">Errors (24 hours)</dt>
        <dd data-testid="errors">{source.errors_24h}</dd>
        {source.last_error && (
          <>
            <dt className="text-muted-foreground">Last error</dt>
            <dd className="break-words">{source.last_error}</dd>
          </>
        )}
      </dl>
      {source.runnable && (
        <div>
          <button
            type="button"
            className={buttonClass}
            disabled={isLoading || source.run_requested}
            onClick={() => void runNow(source.source)}
          >
            {source.run_requested ? 'Run requested…' : 'Run now'}
          </button>
        </div>
      )}
    </li>
  )
}

const MODES: Array<{ mode: FakeMode; label: string }> = [
  { mode: 'normal', label: 'Back to normal' },
  { mode: 'fail', label: 'Make it fail' },
  { mode: 'rate_limit', label: 'Make it rate-limited' },
  { mode: 'invalid', label: 'Send invalid data' },
]

function TestControls({ fake }: { fake: SourceHealth | undefined }) {
  const [setMode, { isLoading }] = useSetFakeModeMutation()
  const [runNow] = useRunSourceNowMutation()
  const current = fake?.test_mode ?? 'normal'
  return (
    <section
      aria-labelledby="test-controls"
      className="flex flex-col gap-2 rounded-lg border border-dashed p-4"
    >
      <h2 id="test-controls" className="font-semibold">
        Test controls (staging only)
      </h2>
      <p className="text-sm text-muted-foreground">
        Make <code>fake_source</code> misbehave to see how System Health reacts. The worker picks up
        a change on its next run; each button also asks it to run now (within about 15 seconds).
        Current mode: <span data-testid="fake-mode">{current}</span>.
      </p>
      <div className="flex flex-wrap gap-2">
        {MODES.map(({ mode, label }) => (
          <button
            key={mode}
            type="button"
            className={buttonClass}
            disabled={isLoading || current === mode}
            onClick={() => {
              void setMode(mode).then(() => runNow('fake_source'))
            }}
          >
            {label}
          </button>
        ))}
      </div>
    </section>
  )
}

/** Data source health (PER-13; PRD 3.3, 3.12). Costs arrive in M1. */
export function SystemHealthPage() {
  const health = useGetSystemHealthQuery(undefined, { pollingInterval: POLL_MS })
  const sources = health.data?.sources ?? []

  return (
    <section aria-labelledby="page-title" className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 id="page-title" className="text-3xl font-semibold tracking-tight">
          System Health
        </h1>
        <p className="text-muted-foreground">
          Each data source&apos;s status, last successful fetch and errors in the last 24 hours.
          Updates every 10 seconds.
        </p>
      </div>

      {health.isLoading && <p role="status">Loading…</p>}
      {health.isError && (
        <NotAvailable reason="the system status could not be loaded from the API. Try reloading." />
      )}
      {health.data && sources.length === 0 && (
        <NotAvailable reason="no data sources are connected yet (real sources arrive in M1)." />
      )}
      {sources.length > 0 && (
        <ul className="flex flex-col divide-y rounded-lg border">
          {sources.map((s) => (
            <SourceRow key={s.source} source={s} />
          ))}
        </ul>
      )}

      {health.data && <NewListings data={health.data.new_listings} />}

      <NotAvailable reason="costs per source and AI spend are shown here from M1." />

      {health.data?.test_controls && (
        <TestControls fake={sources.find((s) => s.source === 'fake_source')} />
      )}
    </section>
  )
}
