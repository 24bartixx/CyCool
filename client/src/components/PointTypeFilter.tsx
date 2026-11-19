import { Bike, Check, Route, Signpost, type LucideIcon } from 'lucide-react'
import type { PointKind } from '../api/planner.ts'
import { POINT_KINDS } from '../lib/points.ts'

const KIND_FILTER: Record<PointKind, { label: string; Icon: LucideIcon }> = {
  segment: { label: 'Cycling lanes', Icon: Route },
  junction: { label: 'Junctions', Icon: Signpost },
  station: { label: 'AMBici stations', Icon: Bike },
}

type Props = {
  value: ReadonlySet<PointKind>
  /** Points still to fix per kind, before this filter is applied. */
  counts: Record<PointKind, number>
  onChange: (kinds: Set<PointKind>) => void
}

/** Multi-select: each button toggles one kind in or out of the worst-points list. */
export default function PointTypeFilter({ value, counts, onChange }: Props) {
  const allOn = POINT_KINDS.every((k) => value.has(k))

  function toggle(kind: PointKind) {
    const next = new Set(value)
    if (next.has(kind)) next.delete(kind)
    else next.add(kind)
    onChange(next)
  }

  return (
    <section aria-labelledby="kinds-h" className="space-y-2.5">
      <div className="flex items-center justify-between gap-3">
        <h2 id="kinds-h" className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
          <span className="grid size-5 place-items-center rounded-full bg-primary text-[11px] text-primary-foreground">3</span>
          Where to look
        </h2>
        {!allOn && (
          <button
            type="button"
            onClick={() => onChange(new Set(POINT_KINDS))}
            className="text-[11px] font-medium text-primary hover:underline focus-visible:outline-2 focus-visible:outline-primary"
          >
            Select all
          </button>
        )}
      </div>
      <div role="group" aria-labelledby="kinds-h" className="grid grid-cols-3 gap-1 rounded-xl bg-background p-1">
        {POINT_KINDS.map((kind) => {
          const { label, Icon } = KIND_FILTER[kind]
          const on = value.has(kind)
          return (
            <button
              key={kind}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(kind)}
              className={`relative flex flex-col items-center gap-0.5 rounded-lg px-1 py-2 text-[11px] font-medium leading-tight transition-colors ${
                on ? 'bg-surface text-primary shadow-sm ring-1 ring-border' : 'text-muted hover:text-foreground'
              }`}
            >
              <span
                aria-hidden
                className={`absolute right-1 top-1 grid size-3.5 place-items-center rounded-[4px] border ${
                  on ? 'border-primary bg-primary text-primary-foreground' : 'border-border-strong'
                }`}
              >
                {on && <Check className="size-2.5" strokeWidth={3} />}
              </span>
              <Icon className="mb-0.5 size-4" aria-hidden />
              <span className="text-center">{label}</span>
              <span className={`tabular-nums ${on ? 'text-muted' : ''}`}>{counts[kind]}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
