import { ClipboardList, MousePointerClick, RotateCcw, Trash2, Undo2 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { Evaluation, MapPointInfo } from '../api/planner.ts'
import { eur } from '../lib/format.ts'
import { FIX_ICON } from '../lib/icons.tsx'
import { pointTitle } from '../lib/points.ts'

type Props = {
  plan: Evaluation['plan']
  pointsById: Map<string, MapPointInfo>
  /** The point picked on the map or in a list: its fixes in the plan are highlighted. */
  selectedId?: string
  /**
   * Scroll the highlighted fixes into view when the selection changes. Only where the plan has a pane of its own:
   * sharing the sidebar with the worst list, it would scroll the list the planner just clicked away.
   */
  revealSelected: boolean
  onRemove: (fixId: string, pointId: string) => void
  onUndo: () => void
  onReset: () => void
  onSelect: (id: string) => void
  busy: boolean
}

export default function PlanList({
  plan,
  pointsById,
  selectedId,
  revealSelected,
  onRemove,
  onUndo,
  onReset,
  onSelect,
  busy,
}: Props) {
  const listRef = useRef<HTMLOListElement>(null)
  // Also re-run when a fix is added at (or removed from) the selected point, so a newly accepted one shows.
  const selectedCount = plan.filter((f) => f.point_id === selectedId).length
  useEffect(() => {
    if (!revealSelected || !selectedCount) return
    const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    listRef.current
      ?.querySelector('[data-selected]')
      ?.scrollIntoView({ block: 'nearest', behavior: smooth ? 'smooth' : 'auto' })
  }, [revealSelected, selectedId, selectedCount])

  return (
    <section aria-labelledby="plan-h" className="space-y-2.5">
      <div className="flex min-h-7 flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <h2 id="plan-h" className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
          <span className="grid size-5 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground">
            <ClipboardList className="size-3" aria-hidden />
          </span>
          Your plan
          {plan.length > 0 && (
            <span className="rounded-full bg-primary-soft px-1.5 py-px text-[11px] tabular-nums tracking-normal text-primary">
              {plan.length}
              <span className="sr-only"> {plan.length === 1 ? 'fix' : 'fixes'}</span>
            </span>
          )}
        </h2>
        {/* Nothing to undo or reset in an empty plan: hide the actions rather than show them greyed out. */}
        {plan.length > 0 && (
          <div className="flex gap-0.5">
            <button
              type="button"
              onClick={onUndo}
              disabled={busy}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-primary transition-colors enabled:hover:bg-primary-soft disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-primary"
            >
              <Undo2 className="size-3.5" aria-hidden /> Undo last
            </button>
            <button
              type="button"
              onClick={onReset}
              disabled={busy}
              title="Remove every fix from the plan"
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted transition-colors enabled:hover:bg-danger-soft enabled:hover:text-danger disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-primary"
            >
              <RotateCcw className="size-3.5" aria-hidden /> Reset
            </button>
          </div>
        )}
      </div>
      {plan.length === 0 ? (
        <div className="flex flex-col items-center gap-1 rounded-xl border border-border bg-surface-2 px-5 py-6 text-center">
          <span className="mb-1.5 grid size-10 place-items-center rounded-full bg-primary-soft text-primary">
            <MousePointerClick className="size-5" aria-hidden />
          </span>
          <p className="text-sm font-medium text-foreground">No fixes yet</p>
          <p className="max-w-60 text-xs leading-relaxed text-muted">
            Pick a point on the map and accept a fix. Its cost comes out of the budget and the map updates.
          </p>
        </div>
      ) : (
        <ol ref={listRef} className="space-y-1">
          {plan.map((f, i) => {
            const Icon = FIX_ICON[f.fix_id]
            const point = pointsById.get(f.point_id)
            const location = point ? pointTitle(point) : f.point_id
            const active = f.point_id === selectedId
            return (
              <li
                key={`${f.fix_id}-${f.point_id}`}
                data-selected={active || undefined}
                className="flex scroll-my-2 items-center gap-1"
              >
                <button
                  type="button"
                  onClick={() => onSelect(f.point_id)}
                  aria-current={active ? 'true' : undefined}
                  className={`grid min-w-0 flex-1 grid-cols-[1.75rem_1fr_auto] items-center gap-2 rounded-lg border px-2 py-1.5 text-left transition-colors ${
                    active ? 'border-primary bg-primary-soft' : 'border-transparent hover:border-border hover:bg-surface-2'
                  }`}
                >
                  <span className={`grid size-7 place-items-center rounded-full text-white ${f.fix_id === 'INT-03' ? 'bg-water' : 'bg-primary'}`}>
                    <Icon className="size-3.5" aria-hidden />
                  </span>
                  <span className="min-w-0">
                    <span className="line-clamp-2 text-sm leading-tight font-medium">
                      {i + 1}. {f.label}
                    </span>
                    <span className="block truncate text-[11px] text-muted">
                      {location}
                      {f.length_m > 0 && ` · ${Math.round(f.length_m)} m of street`}
                    </span>
                  </span>
                  <span className="text-xs font-semibold tabular-nums">{eur(f.cost_eur)}</span>
                </button>
                <button
                  type="button"
                  onClick={() => onRemove(f.fix_id, f.point_id)}
                  disabled={busy}
                  aria-label={`Remove item ${i + 1}, ${f.label} at ${location}`}
                  title="Remove from plan"
                  className="grid size-8 shrink-0 place-items-center rounded-md text-muted transition-colors enabled:hover:bg-danger-soft enabled:hover:text-danger enabled:hover:inset-ring-1 enabled:hover:inset-ring-danger/50 disabled:opacity-50 motion-safe:enabled:hover:[&>svg]:animate-trash-wiggle"
                >
                  <Trash2 className="size-4" aria-hidden />
                </button>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
