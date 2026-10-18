import { useGetHealthQuery } from '@/store/api'

/** Shows whether the dashboard can reach the API. Text, not colour, carries the meaning. */
export function ApiStatus() {
  const { data, isLoading, isError } = useGetHealthQuery()

  let label = 'Checking…'
  if (!isLoading && isError) label = 'Not reachable'
  if (!isLoading && !isError && data?.status === 'ok') label = 'OK'

  return (
    <p className="text-sm text-muted-foreground" role="status">
      API status: <span className="font-medium text-foreground">{label}</span>
    </p>
  )
}
