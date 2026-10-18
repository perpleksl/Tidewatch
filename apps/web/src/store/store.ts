import { configureStore } from '@reduxjs/toolkit'

import { tidewatchApi } from './api'

export function makeStore() {
  return configureStore({
    reducer: {
      [tidewatchApi.reducerPath]: tidewatchApi.reducer,
    },
    middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(tidewatchApi.middleware),
  })
}

export type AppStore = ReturnType<typeof makeStore>
export type RootState = ReturnType<AppStore['getState']>
