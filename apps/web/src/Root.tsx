import { ClerkProvider } from '@clerk/react'
import { Provider } from 'react-redux'
import { Route, Routes, useNavigate } from 'react-router'

import { App } from './App'
import { AuthGate } from './auth/AuthGate'
import { SignInPage } from './auth/SignInPage'
import { makeStore } from './store/store'

const store = makeStore()

/** Routing, sign-in and data store. Only /sign-in is public; everything else needs sign-in. */
export function Root({ publishableKey }: { publishableKey: string }) {
  const navigate = useNavigate()
  return (
    <ClerkProvider
      publishableKey={publishableKey}
      signInUrl="/sign-in"
      afterSignOutUrl="/sign-in"
      routerPush={(to) => navigate(to)}
      routerReplace={(to) => navigate(to, { replace: true })}
    >
      <Routes>
        <Route path="/sign-in/*" element={<SignInPage />} />
        <Route
          path="*"
          element={
            <AuthGate>
              <Provider store={store}>
                <App />
              </Provider>
            </AuthGate>
          }
        />
      </Routes>
    </ClerkProvider>
  )
}
