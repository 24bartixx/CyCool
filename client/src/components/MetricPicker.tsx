import type { MetricId, MetricInfo } from '../api/planner.ts'
import { METRIC_ICON, METRIC_SHORT } from '../lib/icons.tsx'

type Props = { metrics: MetricInfo[]; value: MetricId; onChange: (m: MetricId) => void }

const ORDER: MetricId[] = ['combined', 'heat', 'sun', 'water']
const rank = (id: MetricId) => (ORDER.includes(id) ? ORDER.indexOf(id) : ORDER.length)

export default function MetricPicker({ metrics: unordered, value, onChange }: Props) {
  const metrics = [...unordered].sort((a, b) => rank(a.id) - rank(b.id))
  function onKeyDown(e: React.KeyboardEvent) {
    const i = metrics.findIndex((m) => m.id === value)
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') onChange(metrics[(i + 1) % metrics.length].id)
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') onChange(metrics[(i - 1 + metrics.length) % metrics.length].id)
    else return
    e.preventDefault()
  }

  return (
    <section aria-labelledby="metric-h" className="space-y-2.5">
      <h2 id="metric-h" className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
        <span className="grid size-5 place-items-center rounded-full bg-primary text-[11px] text-primary-foreground">2</span>
        What to improve
      </h2>
      <div role="radiogroup" aria-labelledby="metric-h" className="grid grid-cols-4 gap-1 rounded-xl bg-background p-1" onKeyDown={onKeyDown}>
        {metrics.map((m) => {
          const Icon = METRIC_ICON[m.id]
          const active = m.id === value
          return (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(m.id)}
              className={`flex flex-col items-center gap-1 rounded-lg px-1 py-2 text-[11px] font-medium transition-colors ${
                active ? 'bg-surface text-primary shadow-sm ring-1 ring-border' : 'text-muted hover:text-foreground'
              }`}
            >
              <Icon className="size-4" aria-hidden />
              {METRIC_SHORT[m.id]}
            </button>
          )
        })}
      </div>
    </section>
  )
}
