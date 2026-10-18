import { formatTime } from '@/pages/settings/format'
import type { SourceHealth } from '@/store/api'

/** Status always shows text, not colour alone (CLAUDE.md §4). */
export function statusLabel(source: SourceHealth): string {
  if (source.status === 'ok') return 'OK'
  if (source.status === 'degraded') return 'Degraded'
  const until = source.paused_until ? ` (resumes ${formatTime(source.paused_until)})` : ''
  return `Paused — limit reached${until}`
}
