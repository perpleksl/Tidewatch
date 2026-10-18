import { useId, useState, type FormEvent } from 'react'

import { cn } from '@/lib/utils'
import {
  apiErrorMessage,
  useResetSettingMutation,
  useUpdateSettingMutation,
  type SettingItem,
} from '@/store/api'

import { factorLabel, formatValue, shortDecimal } from './format'

const inputClass =
  'w-full min-w-0 rounded-md border bg-background px-2 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 aria-[invalid=true]:border-red-600'
const buttonClass =
  'rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50'

type Draft = string | Record<string, string> | Array<[string, string]>

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}
}

/** The editable form of a stored value. */
function toDraft(item: SettingItem): Draft {
  const v = item.value
  switch (item.kind) {
    case 'integer':
    case 'usd':
      return String(v)
    case 'weights':
      return Object.fromEntries((item.factors ?? []).map((f) => [f, String(record(v)[f] ?? '')]))
    case 'ai_tier':
      return {
        provider: String(record(v).provider ?? ''),
        model: String(record(v).model ?? ''),
      }
    case 'usd_map':
      return Object.entries(record(v)).map(([k, a]): [string, string] => [k, String(a)])
  }
}

/** What gets sent to the API. The API validates; the dashboard does not second-guess it. */
function fromDraft(item: SettingItem, draft: Draft): unknown {
  if (item.kind === 'usd_map' && Array.isArray(draft)) {
    return Object.fromEntries(draft.filter(([name]) => name.trim() !== ''))
  }
  return draft
}

export function SettingRow({ item }: { item: SettingItem }) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(item))
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [update, { isLoading: saving }] = useUpdateSettingMutation()
  const [reset, { isLoading: resetting }] = useResetSettingMutation()
  const id = useId()
  const errorId = `${id}-error`
  const busy = saving || resetting

  const dirty =
    JSON.stringify(fromDraft(item, draft)) !== JSON.stringify(fromDraft(item, toDraft(item)))

  async function onSave(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSaved(null)
    try {
      const updated = await update({
        key: item.key,
        value: fromDraft(item, draft),
      }).unwrap()
      setDraft(toDraft(updated))
      setSaved('Saved')
    } catch (err) {
      setError(apiErrorMessage(err))
    }
  }

  async function onReset() {
    setError(null)
    setSaved(null)
    try {
      const updated = await reset(item.key).unwrap()
      setDraft(toDraft(updated))
      setSaved('Reset to default')
    } catch (err) {
      setError(apiErrorMessage(err))
    }
  }

  const invalid = error !== null
  const describedBy = invalid ? errorId : undefined

  return (
    <form
      onSubmit={(e) => void onSave(e)}
      aria-label={item.label}
      className="grid gap-2 border-b py-4 last:border-b-0 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] md:gap-6"
      data-testid={`setting-${item.key}`}
    >
      <div className="flex min-w-0 flex-col gap-1">
        <span className="font-medium" id={`${id}-label`}>
          {item.label}
        </span>
        <span className="text-sm text-muted-foreground">
          Current:{' '}
          <span data-testid="current">{formatValue(item.kind, item.value, item.unit)}</span>
        </span>
        <span className="text-sm text-muted-foreground">
          Default:{' '}
          <span data-testid="default">{formatValue(item.kind, item.default_value, item.unit)}</span>
          {' · '}Valid: {item.valid_range}
          {item.prd ? ` · PRD ${item.prd}` : ''}
        </span>
        <code className="break-all text-xs text-muted-foreground">{item.key}</code>
      </div>

      <div className="flex min-w-0 flex-col gap-2">
        <Editor
          item={item}
          draft={draft}
          setDraft={setDraft}
          labelledBy={`${id}-label`}
          invalid={invalid}
          describedBy={describedBy}
        />
        {error && (
          <p id={errorId} role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
        {saved && !error && (
          <p role="status" className="text-sm text-muted-foreground">
            {saved}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="submit" className={buttonClass} disabled={busy || !dirty}>
            Save
          </button>
          <button
            type="button"
            className={buttonClass}
            disabled={busy || item.is_default}
            onClick={() => void onReset()}
          >
            Reset to default
          </button>
        </div>
      </div>
    </form>
  )
}

interface EditorProps {
  item: SettingItem
  draft: Draft
  setDraft: (d: Draft) => void
  labelledBy: string
  invalid: boolean
  describedBy: string | undefined
}

function Editor({ item, draft, setDraft, labelledBy, invalid, describedBy }: EditorProps) {
  const common = { 'aria-invalid': invalid, 'aria-describedby': describedBy }

  if ((item.kind === 'integer' || item.kind === 'usd') && typeof draft === 'string') {
    return (
      <div className="flex items-center gap-2">
        <input
          className={inputClass}
          inputMode="decimal"
          value={draft}
          aria-labelledby={labelledBy}
          onChange={(e) => {
            setDraft(e.target.value)
          }}
          {...common}
        />
        {item.unit && <span className="shrink-0 text-sm text-muted-foreground">{item.unit}</span>}
      </div>
    )
  }

  if (item.kind === 'weights' && !Array.isArray(draft) && typeof draft === 'object') {
    const total = Object.values(draft).reduce((sum, v) => sum + (Number(v) || 0), 0)
    return (
      <fieldset className="grid gap-2" aria-labelledby={labelledBy} {...common}>
        {(item.factors ?? []).map((factor) => (
          <label key={factor} className="grid grid-cols-[minmax(0,1fr)_7rem] items-center gap-2">
            <span className="text-sm">{factorLabel(factor)}</span>
            <input
              className={inputClass}
              inputMode="decimal"
              value={draft[factor] ?? ''}
              onChange={(e) => {
                setDraft({ ...draft, [factor]: e.target.value })
              }}
            />
          </label>
        ))}
        <p className="text-sm text-muted-foreground">Total: {shortDecimal(total)} (must be 1)</p>
      </fieldset>
    )
  }

  if (item.kind === 'ai_tier' && !Array.isArray(draft) && typeof draft === 'object') {
    return (
      <fieldset
        className="grid gap-2 sm:grid-cols-[9rem_minmax(0,1fr)]"
        aria-labelledby={labelledBy}
        {...common}
      >
        <label className="grid gap-1 text-sm">
          Provider
          <select
            className={inputClass}
            value={draft.provider ?? ''}
            onChange={(e) => {
              setDraft({ ...draft, provider: e.target.value })
            }}
          >
            <option value="anthropic">anthropic</option>
            <option value="surplus">surplus</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm">
          Model
          <input
            className={inputClass}
            value={draft.model ?? ''}
            onChange={(e) => {
              setDraft({ ...draft, model: e.target.value })
            }}
          />
        </label>
      </fieldset>
    )
  }

  if (item.kind === 'usd_map' && Array.isArray(draft)) {
    return (
      <fieldset className="grid gap-2" aria-labelledby={labelledBy} {...common}>
        {draft.length === 0 && (
          <p className="text-sm text-muted-foreground">No subscriptions entered yet.</p>
        )}
        {draft.map(([name, amount], index) => (
          <div key={index} className="grid grid-cols-[minmax(0,1fr)_6rem_auto] items-center gap-2">
            <input
              className={inputClass}
              aria-label={`Service ${index + 1} name`}
              placeholder="Service"
              value={name}
              onChange={(e) => {
                setDraft(
                  draft.map((row, i): [string, string] =>
                    i === index ? [e.target.value, row[1]] : row,
                  ),
                )
              }}
            />
            <input
              className={inputClass}
              aria-label={`Service ${index + 1} USD per month`}
              inputMode="decimal"
              placeholder="USD"
              value={amount}
              onChange={(e) => {
                setDraft(
                  draft.map((row, i): [string, string] =>
                    i === index ? [row[0], e.target.value] : row,
                  ),
                )
              }}
            />
            <button
              type="button"
              className={cn(buttonClass, 'px-2')}
              aria-label={`Remove service ${index + 1}`}
              onClick={() => {
                setDraft(draft.filter((_, i) => i !== index))
              }}
            >
              Remove
            </button>
          </div>
        ))}
        <div>
          <button
            type="button"
            className={buttonClass}
            onClick={() => {
              setDraft([...draft, ['', '']])
            }}
          >
            Add service
          </button>
        </div>
      </fieldset>
    )
  }

  return null
}
