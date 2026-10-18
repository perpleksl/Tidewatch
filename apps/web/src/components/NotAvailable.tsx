/**
 * Shown wherever data is missing, always with the reason (PRD 3.9; CLAUDE.md: never render
 * an empty section). Reuse this for any "not available" state.
 */
export function NotAvailable({ reason }: { reason: string }) {
  return (
    <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
      <p>
        <span className="font-medium text-foreground">Not available</span>
        {': '}
        {reason}
      </p>
    </div>
  )
}
