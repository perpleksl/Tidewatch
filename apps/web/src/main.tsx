import { ClerkProvider } from '@clerk/react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Provider } from 'react-redux'

import { App } from './App'
import { AuthGate } from './auth/AuthGate'
import { CLERK_PUBLISHABLE_KEY } from './auth/config'
import { SignInNotConfigured } from './auth/SignInNotConfigured'
import './index.css'
import { makeStore } from './store/store'

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('Root element #root not found')

createRoot(rootElement).render(
  <StrictMode>
    {CLERK_PUBLISHABLE_KEY ? (
      <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY} afterSignOutUrl="/">
        <AuthGate>
          <Provider store={makeStore()}>
            <App />
          </Provider>
        </AuthGate>
      </ClerkProvider>
    ) : (
      <SignInNotConfigured />
    )}
  </StrictMode>,
)
