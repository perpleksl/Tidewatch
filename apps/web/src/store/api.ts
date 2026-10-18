import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

/** Base URL of the Tidewatch API. Set VITE_API_BASE_URL per environment (see .env.example). */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface HealthResponse {
  status: string
}

/** RTK Query API slice. Every later endpoint is added here. */
export const tidewatchApi = createApi({
  reducerPath: 'tidewatchApi',
  baseQuery: fetchBaseQuery({ baseUrl: API_BASE_URL }),
  endpoints: (builder) => ({
    getHealth: builder.query<HealthResponse, void>({
      query: () => '/health',
    }),
  }),
})

export const { useGetHealthQuery } = tidewatchApi
