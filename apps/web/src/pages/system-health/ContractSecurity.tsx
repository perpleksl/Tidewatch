import { NotAvailable } from '@/components/NotAvailable'
import type { ContractSecurity as ContractSecurityT, SecurityItem, TokenRef } from '@/store/api'

import { formatTime } from '@/pages/settings/format'

function label(t: TokenRef) {
  return `${t.name} (${t.ticker}, ${t.chain})`
}

function Items({ items, testId }: { items: SecurityItem[]; testId: string }) {
  return (
    <ul className="flex flex-col gap-2 text-sm" data-testid={testId}>
      {items.map((i) => (
        <li key={`${i.token.chain}-${i.token.name}-${i.token.ticker}`} className="break-words">
          <span className="font-medium">{label(i.token)}</span>: {i.reasons.join('; ')}
          <span className="text-muted-foreground"> (checked {formatTime(i.checked_at)})</span>
        </li>
      ))}
    </ul>
  )
}

/** Contract-security results from GoPlus, including hard stops (PER-23; PRD 3.4). */
export function ContractSecuritySection({ data }: { data: ContractSecurityT | undefined }) {
  return (
    <section aria-labelledby="contract-security" className="flex flex-col gap-2">
      <h2 id="contract-security" className="text-xl font-semibold">
        Contract security
      </h2>
      <p className="text-sm text-muted-foreground">
        GoPlus checks tokens in Mispriced&apos;s market-cap range when they&apos;re found, then once
        a day. A hard stop marks a token &quot;Avoid&quot;: it&apos;s kept off the lists and the
        digest.
      </p>
      {!data ? (
        <NotAvailable reason="contract-security checks are not running on this server yet." />
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-sm" data-testid="sec-summary">
            {data.passed} passed · {data.avoid.length} avoid · {data.unknown.length} unknown
          </p>
          {data.passed + data.avoid.length + data.unknown.length === 0 && (
            <NotAvailable reason="no tokens have been checked yet. Checks start once tokens have a market cap in Mispriced's range." />
          )}
          {data.avoid.length > 0 && (
            <div className="flex flex-col gap-1">
              <h3 className="text-sm font-medium">Avoid (hard stop)</h3>
              <Items items={data.avoid} testId="sec-avoid" />
            </div>
          )}
          {data.unknown.length > 0 && (
            <div className="flex flex-col gap-1">
              <h3 className="text-sm font-medium">Unknown</h3>
              <Items items={data.unknown} testId="sec-unknown" />
            </div>
          )}
          {data.not_applicable.length > 0 && (
            <div className="flex flex-col gap-1">
              <h3 className="text-sm font-medium">Not applicable (native coins)</h3>
              <ul className="flex flex-col gap-1 text-sm" data-testid="sec-na">
                {data.not_applicable.map((t) => (
                  <li key={`${t.chain}-${t.name}`}>
                    {label(t)}: Not applicable (no token contract to check)
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
