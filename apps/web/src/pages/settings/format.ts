import type { SettingKind } from '@/store/api'

const usd = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 })

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}
}

/** Shortens long decimals for display only (stored values stay exact). */
export function shortDecimal(value: unknown): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  return String(Math.round(n * 10_000) / 10_000)
}

export function formatUsd(value: unknown): string {
  const n = Number(value)
  return Number.isFinite(n) ? `$${usd.format(n)}` : String(value)
}

/** A setting value as plain text for the page and the change log. */
export function formatValue(kind: SettingKind, value: unknown, unit = ''): string {
  switch (kind) {
    case 'integer':
      return unit ? `${String(value)} ${unit}` : String(value)
    case 'usd':
      return formatUsd(value)
    case 'weights': {
      const entries = Object.entries(asRecord(value))
      const unique = new Set(entries.map(([, v]) => String(v)))
      if (entries.length > 0 && unique.size === 1) {
        return `Equal (${shortDecimal(entries[0]?.[1])} each)`
      }
      return entries.map(([k, v]) => `${k}: ${shortDecimal(v)}`).join(', ')
    }
    case 'ai_tier': {
      const tier = asRecord(value)
      return `${String(tier.provider)} / ${String(tier.model)}`
    }
    case 'usd_map': {
      const entries = Object.entries(asRecord(value))
      if (entries.length === 0) return 'None entered'
      return entries.map(([k, v]) => `${k}: ${formatUsd(v)}`).join(', ')
    }
  }
}

const copenhagen = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/Copenhagen',
  dateStyle: 'medium',
  timeStyle: 'short',
})

/** Times are stored in UTC and shown in Copenhagen time (CLAUDE.md §4). */
export function formatTime(iso: string): string {
  return copenhagen.format(new Date(iso))
}

/** Factor keys like "smart_wallet_accumulation" as readable labels. */
export function factorLabel(key: string): string {
  const text = key.replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}
