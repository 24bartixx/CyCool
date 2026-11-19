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

/**
 * Multi-select: each row toggles one kind in or out of the worst-points list. Drawn as a checklist, not as tiles,
 * so it doesn't read as another single-choice control like "What to improve" above it.
 */
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
      <fieldset aria-labelledby="kinds-h" className="divide-y divide-border overflow-hidden rounded-xl border border-border">
        {POINT_KINDS.map((kind) => {
          const { label, Icon } = KIND_FILTER[kind]
          const on = value.has(kind)
          return (
            <label
              key={kind}
              className="flex cursor-pointer items-center gap-2.5 px-3 py-2 text-sm transition-colors hover:bg-surface-2 has-[:focus-visible]:bg-surface-2"
            >
              <input type="checkbox" checked={on} onChange={() => toggle(kind)} className="peer sr-only" />
              <span
                aria-hidden
                className={`grid size-4 shrink-0 place-items-center rounded-[5px] border transition-colors peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary ${
                  on ? 'border-primary bg-primary text-primary-foreground' : 'border-border-strong bg-surface'
                }`}
              >
                {on && <Check className="size-3" strokeWidth={3} />}
              </span>
              <Icon className={`size-4 shrink-0 ${on ? 'text-primary' : 'text-muted'}`} aria-hidden />
              <span className={`flex-1 truncate font-medium ${on ? 'text-foreground' : 'text-muted'}`}>{label}</span>
              <span
                className={`rounded-full px-2 py-px text-[11px] font-medium tabular-nums ${
                  on ? 'bg-primary-soft text-primary' : 'bg-background text-muted'
                }`}
              >
                {counts[kind]}
                <span className="sr-only"> to fix</span>
              </span>
            </label>
          )
        })}
      </fieldset>
    </section>
  )
}
