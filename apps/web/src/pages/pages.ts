/**
 * The dashboard's pages, in navigation order (PRD Section 2; diagrams/flow-owner-journeys.md).
 * `milestone` is when the page gets real content (ARCHITECTURE.md Section 11).
 */
export interface PageDef {
  path: string
  title: string
  /** When the page gets real content; only shown while `built` is false. */
  milestone: string
  /** True once the page has real content (no "coming in" placeholder). */
  built: boolean
}

export const PAGES: readonly PageDef[] = [
  {
    path: '/mispriced',
    title: 'Mispriced',
    built: false,
    milestone: 'M1 — Mispriced',
  },
  {
    path: '/narratives',
    title: 'Narratives',
    built: false,
    milestone: 'M2 — Narratives',
  },
  {
    path: '/launches',
    title: 'Launches',
    built: false,
    milestone: 'M3 — Launches',
  },
  {
    path: '/track-record',
    title: 'Track Record',
    built: false,
    milestone: 'M4 — Backtest and release 1',
  },
  {
    path: '/backtest',
    title: 'Backtest',
    built: false,
    milestone: 'M4 — Backtest and release 1',
  },
  {
    path: '/settings',
    title: 'Settings',
    built: true,
    milestone: 'M0 — Foundation (PER-12)',
  },
  {
    path: '/system-health',
    title: 'System Health',
    built: false,
    milestone: 'M1 — Mispriced',
  },
]

/** Where the Owner lands after signing in (PER-11 AC1). */
export const HOME_PATH = '/mispriced'
