import { useGetMeQuery } from '@/store/api'

/** Shows whether the API accepts this sign-in (calls the protected GET /me). */
export function SignInCheck() {
  const { data, isLoading, isError } = useGetMeQuery()

  let label = 'Checking…'
  if (!isLoading && isError) label = 'Not accepted'
  if (!isLoading && !isError && data?.user_id) label = 'OK'

  return (
    <p className="text-sm text-muted-foreground" role="status" aria-label="API sign-in">
      API sign-in: <span className="font-medium text-foreground">{label}</span>
    </p>
  )
}
