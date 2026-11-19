import { RotateCcw, Undo2 } from 'lucide-react'
import type { Evaluation, MapPointInfo } from '../api/planner.ts'
import { eur } from '../lib/format.ts'
import { FIX_ICON } from '../lib/icons.tsx'
import { pointTitle } from '../lib/points.ts'

type Props = {
  plan: Evaluation['plan']
  pointsById: Map<string, MapPointInfo>
  onUndo: () => void
  onReset: () => void
  onSelect: (id: string) => void
  busy: boolean
}

export default function PlanList({ plan, pointsById, onUndo, onReset, onSelect, busy }: Props) {
  return (
    <section aria-labelledby="plan-h" className="space-y-2.5">
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <h2 id="plan-h" className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
          <span className="grid size-5 place-items-center rounded-full bg-primary text-[11px] text-primary-foreground">4</span>
          Your plan ({plan.length})
        </h2>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={onUndo}
            disabled={!plan.length || busy}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-primary-soft disabled:text-muted disabled:opacity-50 disabled:hover:bg-transparent"
          >
            <Undo2 className="size-3.5" aria-hidden /> Undo last
          </button>
          <button
            type="button"
            onClick={onReset}
            disabled={!plan.length || busy}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted hover:bg-background hover:text-foreground disabled:opacity-50"
          >
            <RotateCcw className="size-3.5" aria-hidden /> Reset
          </button>
        </div>
      </div>
      {plan.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border-strong p-3 text-xs leading-relaxed text-muted">
          No fixes yet. Accepted fixes appear here, their cost is taken from the budget and the map updates.
        </p>
      ) : (
        <ol className="space-y-1">
          {plan.map((f, i) => {
            const Icon = FIX_ICON[f.fix_id]
            const p = pointsById.get(f.point_id)
            return (
              <li key={`${f.fix_id}-${f.point_id}`}>
                <button
                  type="button"
                  onClick={() => onSelect(f.point_id)}
                  className="grid w-full grid-cols-[1.75rem_1fr_auto] items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-surface-2"
                >
                  <span className={`grid size-7 place-items-center rounded-full text-white ${f.fix_id === 'INT-03' ? 'bg-water' : 'bg-primary'}`}>
                    <Icon className="size-3.5" aria-hidden />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {i + 1}. {f.label}
                    </span>
                    <span className="block truncate text-[11px] text-muted">{p ? pointTitle(p) : f.point_id}</span>
                  </span>
                  <span className="text-xs font-semibold tabular-nums">{eur(f.cost_eur)}</span>
                </button>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
