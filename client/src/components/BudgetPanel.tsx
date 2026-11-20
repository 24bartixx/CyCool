import { Wallet } from 'lucide-react'
import { useId, useState } from 'react'
import { eur, eurShort } from '../lib/format.ts'
import { MAX_BUDGET } from '../lib/usePlanner.ts'

const PRESETS = [25_000, 50_000, 100_000, 250_000]

/** Remount with `key={budget}` to reset the draft when the budget changes elsewhere (URL, presets). */
type Props = { budget: number; spent: number; onChange: (b: number) => void }

export default function BudgetPanel({ budget, spent, onChange }: Props) {
  const inputId = useId()
  const errorId = useId()
  const [draft, setDraft] = useState(String(budget))
  const [error, setError] = useState<string>()

  function commit(value: string) {
    const n = Number(value.replace(/[^\d.]/g, ''))
    if (!value.trim() || !Number.isFinite(n) || n <= 0) {
      setError('Enter a budget above €0.')
      return
    }
    if (n > MAX_BUDGET) {
      setError(`The prototype accepts budgets up to ${eur(MAX_BUDGET)}.`)
      return
    }
    if (n < spent) {
      setError(`You have already committed ${eur(spent)}. Undo fixes before lowering the budget below that.`)
      return
    }
    setError(undefined)
    if (Math.round(n) !== budget) onChange(n)
  }

  const remaining = Math.max(0, budget - spent)
  const pct = budget > 0 ? Math.min(100, (spent / budget) * 100) : 0

  return (
    <section aria-labelledby={`${inputId}-h`} className="space-y-3">
      <h2 id={`${inputId}-h`} className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
        <span className="grid size-5 place-items-center rounded-full bg-primary text-[11px] text-primary-foreground">1</span>
        Budget
      </h2>
      <div>
        <label htmlFor={inputId} className="sr-only">
          Budget in euros
        </label>
        <div className="flex items-center rounded-lg border border-border-strong bg-surface focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20">
          <Wallet className="ml-3 size-4 text-muted" aria-hidden />
          <span className="ml-2 text-sm text-muted">€</span>
          <input
            id={inputId}
            inputMode="numeric"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={(e) => commit(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && commit((e.target as HTMLInputElement).value)}
            aria-invalid={!!error}
            aria-describedby={error ? errorId : undefined}
            className="w-full bg-transparent px-2 py-2 text-base font-semibold outline-none"
          />
        </div>
        {error && (
          <p id={errorId} role="alert" className="mt-1.5 text-xs text-danger">
            {error}
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Budget presets">
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => commit(String(p))}
              aria-pressed={budget === p}
              className={`rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors ${
                budget === p
                  ? 'border-primary bg-primary-soft text-primary'
                  : 'border-border bg-surface text-muted hover:border-border-strong hover:text-foreground'
              }`}
            >
              {eurShort(p)}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div
          className="h-2 overflow-hidden rounded-full bg-border"
          role="progressbar"
          aria-label="Budget committed"
          aria-valuemin={0}
          aria-valuemax={budget}
          aria-valuenow={spent}
        >
          <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-1.5 flex justify-between text-xs">
          <span className="text-muted">
            Committed <span className="font-semibold text-foreground" title={eur(spent)}>{eurShort(spent)}</span>
          </span>
          <span className="text-muted">
            Left <span className="font-semibold text-foreground" title={eur(remaining)}>{eurShort(remaining)}</span>
          </span>
        </div>
      </div>
    </section>
  )
}
