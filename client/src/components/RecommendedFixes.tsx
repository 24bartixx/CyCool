import { ArrowRight, Check, CircleCheck, Info, LoaderCircle, Thermometer, TriangleAlert } from 'lucide-react'
import { useId } from 'react'
import type { FixImpact, FixOption, MapPointInfo, MetricId, Recommendation } from '../api/planner.ts'
import { dec1, dec2, eurShort } from '../lib/format.ts'
import { FIX_ICON, METRIC_ICON, METRIC_SHORT } from '../lib/icons.tsx'
import ScoreChip from './ScoreChip.tsx'

const IMPACT_LABEL: Record<MetricId, string> = {
  water: 'Drinking water',
  sun: 'Solar index',
  heat: 'Temperature',
  combined: 'Combined',
}

const IMPACT_ICON_STYLE: Record<MetricId, string> = {
  water: 'bg-water-soft text-water',
  sun: 'bg-warning-soft text-warning',
  heat: 'bg-danger-soft text-danger',
  combined: 'bg-surface text-primary',
}

type Props = {
  point: MapPointInfo
  metric: MetricId
  rec: { data?: Recommendation; error?: string; loading: boolean }
  nextWorstId?: string
  busy: boolean
  onAccept: (fixId: string) => void
}

function ImpactRow({ impact }: { impact: FixImpact }) {
  const { metric, before, after } = impact
  const measurement = dec2(before) === dec2(after) ? impact.measurement : undefined
  const label = metric === 'sun' && measurement?.unit === '%' ? 'Red-light sun exposure' : IMPACT_LABEL[metric]
  const Icon = metric === 'heat' ? Thermometer : METRIC_ICON[metric]
  const combined = metric === 'combined'

  return (
    <div className={`col-span-full grid grid-cols-subgrid items-center rounded-lg px-1 py-1 ${combined ? 'mb-1 bg-primary-soft' : ''}`}>
      <dt className={`flex min-w-0 items-center gap-1.5 @max-[14rem]:col-span-full ${combined ? 'font-semibold text-primary' : 'font-medium text-muted'}`}>
        <span className={`grid size-5 shrink-0 place-items-center rounded-md ${IMPACT_ICON_STYLE[metric]}`}>
          <Icon className="size-3.5" aria-hidden />
        </span>
        <span className="wrap-anywhere">{label}</span>
      </dt>
      <dd className="col-span-3 grid grid-cols-subgrid items-center text-right font-medium tabular-nums @max-[14rem]:col-start-2">
        <span className="whitespace-nowrap">
          {measurement ? `${dec1(measurement.before)} ${measurement.unit}` : <ScoreChip score={before} metric={metric} />}
        </span>
        <ArrowRight className="size-3 text-muted" aria-label="to" />
        <span className="whitespace-nowrap">
          {measurement ? `${dec1(measurement.after)} ${measurement.unit}` : <ScoreChip score={after} metric={metric} />}
        </span>
      </dd>
    </div>
  )
}

function OptionCard({ o, best, metric, busy, onAccept }: { o: FixOption; best: boolean; metric: MetricId; busy: boolean; onAccept: () => void }) {
  const Icon = FIX_ICON[o.fix_id]
  const disabled = o.status !== 'available' || busy
  const effectsId = useId()
  const localImpacts: FixImpact[] = o.local_impacts ?? (
    o.local_before != null && o.local_after != null ? [{ metric, before: o.local_before, after: o.local_after }] : []
  )
  const impacts = localImpacts
    .filter((impact) =>
      (impact.metric !== 'combined' || metric === 'combined') &&
      (impact.measurement || dec2(impact.before) !== dec2(impact.after)),
    )
    .sort((a, b) => Number(b.metric === 'combined') - Number(a.metric === 'combined'))
  return (
    <li className={`rounded-xl border bg-surface px-3 py-4 ${best ? 'border-primary shadow-sm ring-1 ring-primary/20' : 'border-border'}`}>
      <div className="flex items-center gap-2">
        <span className={`grid size-7 shrink-0 place-items-center rounded-md text-white ${o.fix_id === 'INT-03' ? 'bg-water' : 'bg-primary'}`}>
          <Icon className="size-3.5" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2">
          <p className="text-sm leading-tight font-semibold">{o.label}</p>
          {best && <span className="rounded-full bg-primary px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-white">Best value</span>}
          {(o.length_m ?? 0) > 0 && (
            <span className="basis-full text-[11px] text-muted" title="Trees and cool pavement are laid along the whole real street segment">
              Along the whole street segment · {Math.round(o.length_m ?? 0)} m
            </span>
          )}
        </div>
        {o.effects.length > 0 && (
          // Effects show on hover, and on keyboard focus for people who can't hover.
          <span className="group relative shrink-0">
            <button
              type="button"
              aria-label={`Effects of ${o.label}`}
              aria-describedby={effectsId}
              className="grid size-6 place-items-center rounded-md text-muted hover:bg-background hover:text-foreground"
            >
              <Info className="size-4" aria-hidden />
            </button>
            <span
              id={effectsId}
              role="tooltip"
              className="invisible absolute right-0 top-full z-10 mt-1 flex w-56 flex-wrap gap-1 rounded-lg border border-border bg-surface p-2 opacity-0 shadow-lg transition-opacity group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
            >
              {o.effects.map((e) => (
                <span key={e} className="rounded-md bg-background px-1.5 py-px text-[11px] text-foreground">
                  {e}
                </span>
              ))}
            </span>
          </span>
        )}
      </div>
      {impacts.length > 0 && (
        <dl aria-label="Changes at this point" className="@container mt-3.5 grid grid-cols-[minmax(0,1fr)_auto_auto_auto] gap-x-1 text-xs leading-tight">
          {impacts.map((impact) => <ImpactRow key={impact.metric} impact={impact} />)}
        </dl>
      )}
      {o.status === 'applied' ? (
        <p className="mt-4 flex items-center gap-1.5 text-sm font-medium text-success">
          <CircleCheck className="size-4" aria-hidden /> Already in your plan
        </p>
      ) : (
        <>
          <button
            type="button"
            onClick={onAccept}
            disabled={disabled}
            className="mt-4 inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-border disabled:text-muted"
          >
            <Check className="size-4" aria-hidden /> Accept for {eurShort(o.cost_eur)}
          </button>
          {o.status === 'over_budget' && (
            <p className="mt-2.5 flex items-center gap-1 text-xs text-warning">
              <TriangleAlert className="size-3.5" aria-hidden /> Costs more than the budget left.
            </p>
          )}
        </>
      )}
    </li>
  )
}

export default function RecommendedFixes({ point, metric, rec, nextWorstId, busy, onAccept }: Props) {
  const options = rec.data?.point_id === point.id ? rec.data.options : undefined
  const useful = options?.filter((o) => o.status === 'available' || o.status === 'over_budget' || o.status === 'applied') ?? []
  const bestId = options?.find((o) => o.status === 'available')?.fix_id

  return (
    <section aria-labelledby="recs-h" aria-busy={rec.loading}>
      <div className="mb-4">
        <div className="flex items-center justify-between">
          <h3 id="recs-h" className="text-sm font-semibold">
            Recommended fixes
          </h3>
          {rec.loading && <LoaderCircle className="size-4 animate-spin text-muted" aria-label="Loading" />}
        </div>
      </div>
      {rec.error && (
        <p role="alert" className="rounded-lg bg-danger-soft p-2.5 text-xs text-danger">
          Couldn't load recommendations: {rec.error}
        </p>
      )}
      {!options && !rec.error && (
        <div className="space-y-2">
          <div className="cc-skeleton h-28" />
          <div className="cc-skeleton h-20" />
        </div>
      )}
      {options && useful.length === 0 && (
        <p className="rounded-lg border border-border p-3 text-xs text-muted">
          No catalogue fix improves {METRIC_SHORT[metric].toLowerCase()} at this point.
          {nextWorstId && ' Try the next worst point.'}
        </p>
      )}
      {useful.length > 0 && (
        <ul className="space-y-2">
          {useful.map((o) => (
            <OptionCard key={o.fix_id} o={o} best={o.fix_id === bestId} metric={metric} busy={busy} onAccept={() => onAccept(o.fix_id)} />
          ))}
        </ul>
      )}
    </section>
  )
}
