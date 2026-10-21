import { getToken } from '@clerk/react'
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

/** Base URL of the Tidewatch API. Set VITE_API_BASE_URL per environment (see .env.example). */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface HealthResponse {
  status: string
}

export interface MeResponse {
  user_id: string
}

export type SettingKind = 'integer' | 'usd' | 'weights' | 'ai_tier' | 'usd_map'

/** One setting as the API returns it (PER-12). Values are JSON; see backend db/settings.py. */
export interface SettingItem {
  key: string
  area: string
  label: string
  kind: SettingKind
  unit: string
  valid_range: string
  prd: string
  value: unknown
  default_value: unknown
  is_default: boolean
  factors: string[] | null
}

export interface SettingChangeItem {
  key: string
  label: string
  old_value: unknown
  new_value: unknown
  changed_at: string
  reason: string | null
}

export interface SourceHealth {
  source: string
  status: 'ok' | 'degraded' | 'paused'
  last_success_at: string | null
  last_attempt_at: string | null
  paused_until: string | null
  errors_24h: number
  last_error: string | null
  run_requested: boolean
  test_mode: string | null
  /** False for entries that aren't data sources (e.g. the AI marketplace). */
  runnable: boolean
}

export interface NewListing {
  coingecko_id: string
  name: string
  /** Display only; tokens are never identified by ticker. */
  symbol: string
  chains: string[]
  outcome: 'assessed' | 'outside_universe' | 'unresolved'
  reason: string | null
  candidate_tab: 'launches' | 'mispriced' | null
  first_seen_at: string
}

export interface NewListings {
  /** When the starting list was recorded; null until discovery has run once. */
  starting_list_at: string | null
  items: NewListing[]
}

export interface CoinGeckoUsage {
  calls_this_month: number
  allowance: number
  projected_month_end: number
  /** The projection is above the free plan's allowance. */
  projected_over: boolean
}

export interface TokenRef {
  name: string
  ticker: string
  chain: string
}

export interface PriceDisagreement {
  token: TokenRef
  /** Decimal as a string, e.g. "10.5". */
  spread_percent: string
  used_source: string
  sources: Array<{ source: string; price: string; volume_24h: string }>
}

export interface MarketData {
  tokens_with_coingecko_id: number
  tokens_without_coingecko_id: number
  without_coingecko_id: TokenRef[]
  price_disagreements: PriceDisagreement[]
}

export interface SystemHealth {
  sources: SourceHealth[]
  /** True on non-production environments: fake_source can be made to misbehave. */
  test_controls: boolean
  /** PER-19. Missing on an API version from before PER-19. */
  new_listings?: NewListings
  /** PER-20. Missing on an API version from before PER-20. */
  coingecko_usage?: CoinGeckoUsage
  market_data?: MarketData
}

export type FakeMode = 'normal' | 'fail' | 'rate_limit' | 'invalid'

/** The message the API sends when it refuses a value (shown inline next to the field). */
export function apiErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'data' in error) {
    const data = (error as { data: unknown }).data
    if (typeof data === 'object' && data !== null && 'detail' in data) {
      const detail = (data as { detail: unknown }).detail
      if (typeof detail === 'string') return detail
    }
  }
  return 'Could not save. Check your connection and try again.'
}

/** RTK Query API slice. Every later endpoint is added here. */
export const tidewatchApi = createApi({
  reducerPath: 'tidewatchApi',
  baseQuery: fetchBaseQuery({
    baseUrl: API_BASE_URL,
    // Every request carries the Clerk session token; the API rejects requests without one
    // (except /health). Clerk refreshes the short-lived token automatically.
    prepareHeaders: async (headers) => {
      const token = await getToken()
      if (token) headers.set('Authorization', `Bearer ${token}`)
      return headers
    },
  }),
  tagTypes: ['Settings', 'SystemHealth'],
  endpoints: (builder) => ({
    // `void` = this endpoint takes no argument (the documented RTK Query pattern).
    // eslint-disable-next-line @typescript-eslint/no-invalid-void-type
    getHealth: builder.query<HealthResponse, void>({
      query: () => '/health',
    }),
    // eslint-disable-next-line @typescript-eslint/no-invalid-void-type
    getMe: builder.query<MeResponse, void>({
      query: () => '/me',
    }),
    // eslint-disable-next-line @typescript-eslint/no-invalid-void-type
    getSettings: builder.query<SettingItem[], void>({
      query: () => '/settings',
      providesTags: ['Settings'],
    }),
    // eslint-disable-next-line @typescript-eslint/no-invalid-void-type
    getSettingChanges: builder.query<SettingChangeItem[], void>({
      query: () => '/settings-changes',
      providesTags: ['Settings'],
    }),
    updateSetting: builder.mutation<SettingItem, { key: string; value: unknown }>({
      query: ({ key, value }) => ({
        url: `/settings/${encodeURIComponent(key)}`,
        method: 'PUT',
        body: { value },
      }),
      invalidatesTags: ['Settings'],
    }),
    // eslint-disable-next-line @typescript-eslint/no-invalid-void-type
    getSystemHealth: builder.query<SystemHealth, void>({
      query: () => '/system-health',
      providesTags: ['SystemHealth'],
    }),
    runSourceNow: builder.mutation<SourceHealth, string>({
      query: (source) => ({
        url: `/system-health/${encodeURIComponent(source)}/run`,
        method: 'POST',
      }),
      invalidatesTags: ['SystemHealth'],
    }),
    setFakeMode: builder.mutation<SourceHealth, FakeMode>({
      query: (mode) => ({
        url: '/system-health/fake_source/test-mode',
        method: 'POST',
        body: { mode },
      }),
      invalidatesTags: ['SystemHealth'],
    }),
    resetSetting: builder.mutation<SettingItem, string>({
      query: (key) => ({
        url: `/settings/${encodeURIComponent(key)}/reset`,
        method: 'POST',
      }),
      invalidatesTags: ['Settings'],
    }),
  }),
})

export const {
  useGetHealthQuery,
  useGetMeQuery,
  useGetSettingsQuery,
  useGetSettingChangesQuery,
  useUpdateSettingMutation,
  useResetSettingMutation,
  useGetSystemHealthQuery,
  useRunSourceNowMutation,
  useSetFakeModeMutation,
} = tidewatchApi
