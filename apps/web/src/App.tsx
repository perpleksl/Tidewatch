import { Navigate, Route, Routes } from 'react-router'

import { ApiStatus } from '@/components/ApiStatus'
import { SignInCheck } from '@/components/SignInCheck'
import { SiteHeader } from '@/components/SiteHeader'
import { NotFoundPage, PlaceholderPage } from '@/pages/PlaceholderPage'
import { HOME_PATH, PAGES } from '@/pages/pages'
import { SettingsPage } from '@/pages/settings/SettingsPage'
import { SystemHealthPage } from '@/pages/system-health/SystemHealthPage'

/** The signed-in dashboard: header, the current page, and connection status at the bottom. */
export function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 px-4 py-8">
        <Routes>
          <Route index element={<Navigate to={HOME_PATH} replace />} />
          {PAGES.map((page) => (
            <Route
              key={page.path}
              path={page.path.slice(1)}
              element={
                page.path === '/settings' ? (
                  <SettingsPage />
                ) : page.path === '/system-health' ? (
                  <SystemHealthPage />
                ) : (
                  <PlaceholderPage page={page} />
                )
              }
            />
          ))}
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
      <footer className="mx-auto flex w-full max-w-5xl flex-wrap gap-x-6 gap-y-1 border-t px-4 py-3">
        <ApiStatus />
        <SignInCheck />
      </footer>
    </div>
  )
}
