import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'

import { CLERK_PUBLISHABLE_KEY } from './auth/config'
import { SignInNotConfigured } from './auth/SignInNotConfigured'
import './index.css'
import { Root } from './Root'

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('Root element #root not found')

createRoot(rootElement).render(
  <StrictMode>
    {CLERK_PUBLISHABLE_KEY ? (
      <BrowserRouter>
        <Root publishableKey={CLERK_PUBLISHABLE_KEY} />
      </BrowserRouter>
    ) : (
      <SignInNotConfigured />
    )}
  </StrictMode>,
)
