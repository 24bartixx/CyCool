import { Users } from 'lucide-react'
import type { MapPointInfo, MetricId, PointResult } from '../api/planner.ts'
import { int } from '../lib/format.ts'
import { METRIC_SHORT } from '../lib/icons.tsx'
import { KIND_SHORT, pointTitle } from '../lib/points.ts'
import ScoreChip from './ScoreChip.tsx'

type Props = {
  metric: MetricId
  worst: string[]
  pointsById: Map<string, MapPointInfo>
  resultsById: Map<string, PointResult>
  selectedId?: string
  onSelect: (id: string) => void
  onHover: (id?: string) => void
}

export default function WorstList({ metric, worst, pointsById, resultsById, selectedId, onSelect, onHover }: Props) {
  const top = worst.length ? (resultsById.get(worst[0])?.priority ?? 0) : 0
  return (
    <section aria-labelledby="worst-h" className="space-y-2.5">
      <div className="flex items-baseline justify-between">
        <h2 id="worst-h" className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
          <span className="grid size-5 place-items-center rounded-full bg-primary text-[11px] text-primary-foreground">3</span>
          Worst points · {METRIC_SHORT[metric]}
        </h2>
      </div>
      <p className="text-xs text-muted">Ranked by score × spring riders × length. Pick one to see fixes.</p>
      {worst.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border-strong p-3 text-sm text-muted">
          Nothing left to improve for this metric on the trails.
        </p>
      ) : (
        <ol className="space-y-1">
          {worst.map((id, i) => {
            const p = pointsById.get(id)
            const r = resultsById.get(id)
            if (!p || !r) return null
            const active = id === selectedId
            return (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => onSelect(id)}
                  onMouseEnter={() => onHover(id)}
                  onMouseLeave={() => onHover(undefined)}
                  onFocus={() => onHover(id)}
                  onBlur={() => onHover(undefined)}
                  aria-current={active ? 'true' : undefined}
                  className={`group grid w-full grid-cols-[1.5rem_1fr_auto] items-center gap-2 rounded-lg border px-2 py-1.5 text-left transition-colors ${
                    active ? 'border-primary bg-primary-soft' : 'border-transparent hover:border-border hover:bg-surface-2'
                  }`}
                >
                  <span
                    className={`grid size-6 place-items-center rounded-md text-xs font-semibold ${
                      i === 0 ? 'bg-score-5 text-white' : 'bg-background text-muted'
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{pointTitle(p)}</span>
                    <span className="flex items-center gap-2 overflow-hidden whitespace-nowrap text-[11px] text-muted">
                      <span>{p.trail_id}</span>
                      {p.kind !== 'segment' && <span>{KIND_SHORT[p.kind]}</span>}
                      <span className="inline-flex items-center gap-0.5">
                        <Users className="size-3" aria-hidden />
                        {int(p.riders_spring)}/day
                      </span>
                    </span>
                    <span className="mt-1 block h-1 overflow-hidden rounded-full bg-border" aria-hidden>
                      <span
                        className="block h-full rounded-full bg-score-3"
                        style={{ width: `${top > 0 ? (r.priority / top) * 100 : 0}%` }}
                      />
                    </span>
                  </span>
                  <ScoreChip score={r.scores[metric]} />
                </button>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
