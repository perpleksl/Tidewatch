import { NotAvailable } from '@/components/NotAvailable'
import type { NewListing, NewListings as NewListingsData } from '@/store/api'

import { formatTime } from '@/pages/settings/format'

const OUTCOME_LABEL: Record<NewListing['outcome'], string> = {
  assessed: 'Assessed',
  outside_universe: 'Outside the covered universe',
  unresolved: 'Unresolved',
}

const TAB_LABEL: Record<NonNullable<NewListing['candidate_tab']>, string> = {
  launches: 'Launches',
  mispriced: 'Mispriced',
}

function reasonFor(data: NewListingsData | undefined): string {
  if (!data) return 'new-listing discovery is not running on this server yet.'
  if (!data.starting_list_at) {
    return 'CoinGecko discovery has not run yet. Its first run records the starting list.'
  }
  return `no new listings in the last 7 days (starting list recorded on ${formatTime(data.starting_list_at)}).`
}

/** Coins newly listed on CoinGecko in the last 7 days (PER-19; PRD 3.2). */
export function NewListings({ data }: { data: NewListingsData | undefined }) {
  const items = data?.items ?? []
  return (
    <section aria-labelledby="new-listings" className="flex flex-col gap-2">
      <h2 id="new-listings" className="text-xl font-semibold">
        New listings (last 7 days)
      </h2>
      <p className="text-sm text-muted-foreground">
        Coins that appeared on CoinGecko since the previous daily check. Assessed coins go on to
        meme classification and scoring; the tab shows where they would be considered.
      </p>
      {items.length === 0 ? (
        <NotAvailable reason={reasonFor(data)} />
      ) : (
        <ul className="flex flex-col divide-y rounded-lg border" data-testid="new-listings-list">
          {items.map((item) => (
            <li
              key={item.coingecko_id}
              className="flex flex-col gap-1 px-4 py-3"
              data-testid={`listing-${item.coingecko_id}`}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium break-words">
                  {item.name}{' '}
                  <span className="text-sm text-muted-foreground uppercase">{item.symbol}</span>
                </span>
                <span className="text-sm text-muted-foreground">
                  First seen {formatTime(item.first_seen_at)}
                </span>
              </div>
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted-foreground">Chain</dt>
                <dd data-testid="chain">
                  {item.chains.length > 0 ? item.chains.join(', ') : 'Not available'}
                </dd>
                <dt className="text-muted-foreground">Outcome</dt>
                <dd data-testid="outcome" className="break-words">
                  {OUTCOME_LABEL[item.outcome]}
                  {item.reason && item.reason !== OUTCOME_LABEL[item.outcome]
                    ? ` — ${item.reason}`
                    : ''}
                </dd>
                <dt className="text-muted-foreground">Candidate tab</dt>
                <dd data-testid="tab">
                  {item.candidate_tab ? TAB_LABEL[item.candidate_tab] : 'None'}
                </dd>
              </dl>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
