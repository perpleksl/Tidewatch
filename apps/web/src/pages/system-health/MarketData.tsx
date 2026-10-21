import { NotAvailable } from '@/components/NotAvailable'
import type { CoinGeckoUsage, MarketData as MarketDataT, TokenRef } from '@/store/api'

const OLD_API = 'market data is not running on this server yet.'

function tokenLabel(t: TokenRef) {
  return `${t.name} (${t.ticker}, ${t.chain})`
}

const number = new Intl.NumberFormat('en-GB')

/** CoinGecko calls this month against the free plan's allowance (PER-20). */
export function CoinGeckoUsageSection({ usage }: { usage: CoinGeckoUsage | undefined }) {
  return (
    <section aria-labelledby="coingecko-usage" className="flex flex-col gap-2">
      <h2 id="coingecko-usage" className="text-xl font-semibold">
        CoinGecko usage
      </h2>
      {!usage ? (
        <NotAvailable reason={OLD_API} />
      ) : (
        <div className="flex flex-col gap-1 rounded-lg border p-4 text-sm" data-testid="cg-usage">
          <p>
            CoinGecko calls this month:{' '}
            <span className="font-medium" data-testid="cg-calls">
              {number.format(usage.calls_this_month)} of {number.format(usage.allowance)}
            </span>
          </p>
          <p className="text-muted-foreground">
            Projected by month end: {number.format(usage.projected_month_end)}
          </p>
          {usage.projected_over && (
            <p className="font-medium text-amber-800" role="alert" data-testid="cg-warning">
              Warning: on this pace the free plan&apos;s monthly allowance runs out before the month
              ends. Tidewatch never upgrades the plan; consider refreshing less often or moving
              prices to another source.
            </p>
          )}
        </div>
      )}
    </section>
  )
}

/** Which tracked tokens can get market data, and where sources disagree (PER-20). */
export function MarketDataSection({ data }: { data: MarketDataT | undefined }) {
  return (
    <section aria-labelledby="market-data" className="flex flex-col gap-2">
      <h2 id="market-data" className="text-xl font-semibold">
        Market data
      </h2>
      {!data ? (
        <NotAvailable reason={OLD_API} />
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-sm" data-testid="md-coverage">
            {number.format(data.tokens_with_coingecko_id)} tracked tokens get prices from CoinGecko;{' '}
            {number.format(data.tokens_without_coingecko_id)} can&apos;t.
          </p>
          {data.without_coingecko_id.length > 0 && (
            <div className="flex flex-col gap-1">
              <h3 className="text-sm font-medium">Without market data</h3>
              <ul className="flex flex-col gap-1 text-sm" data-testid="md-missing">
                {data.without_coingecko_id.map((t) => (
                  <li key={`${t.chain}-${t.name}-${t.ticker}`} className="break-words">
                    {tokenLabel(t)} — Not available: not listed on CoinGecko
                  </li>
                ))}
              </ul>
              {data.tokens_without_coingecko_id > data.without_coingecko_id.length && (
                <p className="text-sm text-muted-foreground">
                  and {data.tokens_without_coingecko_id - data.without_coingecko_id.length} more
                </p>
              )}
            </div>
          )}
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-medium">Price disagreements (over 5%)</h3>
            {data.price_disagreements.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                None: every token&apos;s sources agree within 5%.
              </p>
            ) : (
              <ul className="flex flex-col gap-2 text-sm" data-testid="md-disagreements">
                {data.price_disagreements.map((d) => (
                  <li key={`${d.token.chain}-${d.token.name}`} className="break-words">
                    <span className="font-medium">{tokenLabel(d.token)}</span>: sources{' '}
                    {d.spread_percent}% apart (
                    {d.sources.map((s) => `${s.source} $${s.price}`).join(', ')}). Using{' '}
                    {d.used_source}, the busier market.
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
