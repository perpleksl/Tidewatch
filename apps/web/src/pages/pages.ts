/**
 * The dashboard's pages, in navigation order (PRD Section 2; diagrams/flow-owner-journeys.md).
 * `milestone` is when the page gets real content (ARCHITECTURE.md Section 11).
 */
export interface PageDef {
  path: string
  title: string
  milestone: string
}

export const PAGES: readonly PageDef[] = [
  { path: '/mispriced', title: 'Mispriced', milestone: 'M1 — Mispriced' },
  { path: '/narratives', title: 'Narratives', milestone: 'M2 — Narratives' },
  { path: '/launches', title: 'Launches', milestone: 'M3 — Launches' },
  { path: '/track-record', title: 'Track Record', milestone: 'M4 — Backtest and release 1' },
  { path: '/backtest', title: 'Backtest', milestone: 'M4 — Backtest and release 1' },
  { path: '/settings', title: 'Settings', milestone: 'M1 — Mispriced' },
  { path: '/system-health', title: 'System Health', milestone: 'M1 — Mispriced' },
]

/** Where the Owner lands after signing in (PER-11 AC1). */
export const HOME_PATH = '/mispriced'
