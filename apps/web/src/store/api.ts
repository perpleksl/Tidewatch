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
  }),
})

export const { useGetHealthQuery, useGetMeQuery } = tidewatchApi
