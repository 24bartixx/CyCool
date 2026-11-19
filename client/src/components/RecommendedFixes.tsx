import { ArrowRight, Check, CircleCheck, Info, LoaderCircle, TriangleAlert } from 'lucide-react'
import { useId } from 'react'
import type { FixImpact, FixOption, MapPointInfo, MetricId, Recommendation } from '../api/planner.ts'
import { dec1, dec2, eur } from '../lib/format.ts'
import { FIX_ICON, METRIC_SHORT } from '../lib/icons.tsx'
import ScoreChip from './ScoreChip.tsx'

const METRIC_SUBJECT: Record<MetricId, string> = {
  water: 'water access',
  sun: 'solar radiation',
  heat: 'heat stress',
  combined: 'overall cycling comfort',
}

const IMPACT_LABEL: Record<MetricId, string> = {
  water: 'Drinking water',
  sun: 'Solar radiation',
  heat: 'Temperature',
  combined: 'Combined',
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

  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd className="flex items-center gap-1 font-medium tabular-nums">
        {measurement ? <span>{dec1(measurement.before)} {measurement.unit}</span> : <ScoreChip score={before} />}
        <ArrowRight className="size-3 shrink-0 text-muted" aria-label="to" />
        {measurement ? <span>{dec1(measurement.after)} {measurement.unit}</span> : <ScoreChip score={after} />}
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
  const impacts = localImpacts.filter((impact) =>
    (impact.metric !== 'combined' || metric === 'combined') &&
    (impact.measurement || dec2(impact.before) !== dec2(impact.after)),
  )
  return (
    <li className={`rounded-xl border bg-surface px-3 py-4 ${best ? 'border-primary shadow-sm ring-1 ring-primary/20' : 'border-border'}`}>
      <div className="flex items-center gap-2">
        <span className={`grid size-7 shrink-0 place-items-center rounded-md text-white ${o.fix_id === 'INT-03' ? 'bg-water' : 'bg-primary'}`}>
          <Icon className="size-3.5" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2">
          <p className="text-sm leading-tight font-semibold">{o.label}</p>
          {best && <span className="rounded-full bg-primary px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-white">Best value</span>}
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
        <dl aria-label="Changes at this point" className="mt-3.5 space-y-1.5 text-xs leading-tight">
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
            <Check className="size-4" aria-hidden /> Accept for {eur(o.cost_eur)}
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
  const noEffect = options?.filter((o) => o.status === 'no_effect') ?? []
  const bestId = options?.find((o) => o.status === 'available')?.fix_id

  return (
    <section aria-labelledby="recs-h" aria-busy={rec.loading}>
      <div className="mb-2">
        <div className="flex items-center justify-between">
          <h3 id="recs-h" className="text-sm font-semibold">
            Recommended fixes
          </h3>
          {rec.loading && <LoaderCircle className="size-4 animate-spin text-muted" aria-label="Loading" />}
        </div>
        <p className="text-xs text-muted">Fixes for {METRIC_SUBJECT[metric]}</p>
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
        <p className="rounded-lg border border-dashed border-border-strong p-3 text-xs text-muted">
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
      {noEffect.length > 0 && (
        <p className="mt-3 text-xs text-muted">
          Not shown, no effect on {METRIC_SHORT[metric].toLowerCase()} here: {noEffect.map((o) => o.label).join(', ')}.
        </p>
      )}
    </section>
  )
}
