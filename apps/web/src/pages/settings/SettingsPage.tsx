import { NotAvailable } from '@/components/NotAvailable'
import { useGetSettingChangesQuery, useGetSettingsQuery, type SettingItem } from '@/store/api'

import { formatTime, formatValue } from './format'
import { SettingRow } from './SettingRow'

function byArea(items: SettingItem[]): Array<[string, SettingItem[]]> {
  const groups = new Map<string, SettingItem[]>()
  for (const item of items) groups.set(item.area, [...(groups.get(item.area) ?? []), item])
  return [...groups.entries()]
}

/**
 * Every calibration value, grouped by area, editable with "Reset to default", plus the change
 * log (PER-12; PRD 3.13). The API validates every change; refusals show next to the field.
 */
export function SettingsPage() {
  const settings = useGetSettingsQuery()
  const changes = useGetSettingChangesQuery()

  return (
    <section aria-labelledby="page-title" className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 id="page-title" className="text-3xl font-semibold tracking-tight">
          Settings
        </h1>
        <p className="text-muted-foreground">
          Thresholds, weights and AI models. Defaults come from the PRD; tune them after backtests.
          Every change is logged below.
        </p>
      </div>

      {settings.isLoading && <p role="status">Loading settings…</p>}
      {settings.isError && (
        <NotAvailable reason="the settings could not be loaded from the API. Try reloading." />
      )}

      {settings.data &&
        byArea(settings.data).map(([area, items]) => (
          <section key={area} aria-labelledby={`area-${area}`} className="rounded-lg border px-4">
            <h2 id={`area-${area}`} className="pt-4 text-lg font-semibold">
              {area}
            </h2>
            {items.map((item) => (
              <SettingRow key={`${item.key}:${JSON.stringify(item.value)}`} item={item} />
            ))}
          </section>
        ))}

      <section aria-labelledby="change-log" className="flex flex-col gap-2">
        <h2 id="change-log" className="text-lg font-semibold">
          Change log
        </h2>
        {changes.isError && (
          <NotAvailable reason="the change log could not be loaded from the API." />
        )}
        {changes.data?.length === 0 && <NotAvailable reason="no settings have been changed yet." />}
        {changes.data && changes.data.length > 0 && (
          <ol className="flex flex-col divide-y rounded-lg border" data-testid="change-log">
            {changes.data.map((change) => {
              const kind = settings.data?.find((s) => s.key === change.key)?.kind ?? 'integer'
              const unit = settings.data?.find((s) => s.key === change.key)?.unit ?? ''
              return (
                <li
                  key={`${change.changed_at}-${change.key}`}
                  className="flex flex-col gap-1 px-4 py-3 text-sm"
                >
                  <span className="text-muted-foreground">
                    <time dateTime={change.changed_at}>{formatTime(change.changed_at)}</time>
                    {change.reason ? ` · ${change.reason}` : ''}
                  </span>
                  <span className="font-medium">{change.label}</span>
                  <span className="break-words">
                    {formatValue(kind, change.old_value, unit)} →{' '}
                    {formatValue(kind, change.new_value, unit)}
                  </span>
                </li>
              )
            })}
          </ol>
        )}
      </section>
    </section>
  )
}
