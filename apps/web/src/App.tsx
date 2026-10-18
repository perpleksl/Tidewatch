import { ApiStatus } from '@/components/ApiStatus'

export function App() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-4 px-4 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Tidewatch</h1>
      <p className="text-muted-foreground">
        Crypto research dashboard. Placeholder page: features arrive milestone by milestone.
      </p>
      <ApiStatus />
    </main>
  )
}
