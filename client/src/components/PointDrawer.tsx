import { ArrowRight, Check, CircleCheck, Clock, Info, LoaderCircle, MapPin, TriangleAlert, Users, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { FixOption, MapPointInfo, MetricId, PointResult, Recommendation, Trail } from '../api/planner.ts'
import { celsius, dec2, eur, int, metres } from '../lib/format.ts'
import { FIX_ICON, METRIC_ICON, METRIC_SHORT } from '../lib/icons.tsx'
import { KIND_LABEL, pointSubtitle, pointTitle } from '../lib/points.ts'
import { scoreColor } from '../lib/scale.ts'
import ScoreChip from './ScoreChip.tsx'

type Props = {
  point: MapPointInfo
  trail?: Trail
  result?: PointResult
  metric: MetricId
  rec: { data?: Recommendation; error?: string; loading: boolean }
  isWorst: boolean
  nextWorstId?: string
  busy: boolean
  solarUnit: string
  onAccept: (fixId: string) => void
  onClose: () => void
  onGoTo: (id: string) => void
}

function MetricRow({ metric, active, score, detail }: { metric: MetricId; active: boolean; score: number; detail: string }) {
  const Icon = METRIC_ICON[metric]
  return (
    <div className={`rounded-lg px-2.5 py-2 ${active ? 'bg-primary-soft ring-1 ring-primary/30' : ''}`}>
      <div className="flex items-center gap-2">
        <Icon className={`size-4 ${active ? 'text-primary' : 'text-muted'}`} aria-hidden />
        <span className="text-sm font-medium">{METRIC_SHORT[metric]}</span>
        <span className="ml-auto">
          <ScoreChip score={score} showLabel />
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-border" aria-hidden>
        <div className="h-full rounded-full" style={{ width: `${Math.max(2, score * 100)}%`, background: scoreColor(score) }} />
      </div>
      <p className="mt-1 text-xs text-muted">{detail}</p>
    </div>
  )
}

function OptionCard({ o, best, metric, busy, onAccept }: { o: FixOption; best: boolean; metric: MetricId; busy: boolean; onAccept: () => void }) {
  const Icon = FIX_ICON[o.fix_id]
  const disabled = o.status !== 'available' || busy
  return (
    <li className={`rounded-xl border bg-surface p-3 ${best ? 'border-primary shadow-sm ring-1 ring-primary/20' : 'border-border'}`}>
      <div className="flex items-start gap-2.5">
        <span className={`grid size-8 shrink-0 place-items-center rounded-lg text-white ${o.fix_id === 'INT-03' ? 'bg-water' : 'bg-primary'}`}>
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2">
            <p className="font-semibold">{o.label}</p>
            {best && <span className="rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">Best value</span>}
          </div>
          <p className="text-xs text-muted">
            {o.fix_id} · {eur(o.cost_eur)}
            {o.opex_eur_yr ? ` + ${eur(o.opex_eur_yr)}/yr upkeep` : ''}
          </p>
        </div>
      </div>
      <ul className="mt-2 flex flex-wrap gap-1">
        {o.effects.map((e) => (
          <li key={e} className="rounded-md bg-background px-1.5 py-0.5 text-[11px] text-foreground">
            {e}
          </li>
        ))}
      </ul>
      {o.local_before != null && o.local_after != null && (
        <dl className="mt-2.5 grid grid-cols-2 gap-2 text-xs">
          <div>
            <dt className="text-muted">{METRIC_SHORT[metric]} here</dt>
            <dd className="mt-0.5 flex items-center gap-1 font-medium">
              <ScoreChip score={o.local_before} /> <ArrowRight className="size-3 text-muted" aria-label="to" /> <ScoreChip score={o.local_after} />
            </dd>
          </div>
          <div>
            <dt className="text-muted" title="Share of the whole trail network's remaining priority for this metric that the fix removes">
              Network improvement
            </dt>
            <dd className="mt-0.5 font-semibold tabular-nums">
              {dec2(o.network_reduction_pct)} %{' '}
              <span className="font-normal text-muted">({dec2(o.value_pct_per_10k)} % per €10k)</span>
            </dd>
          </div>
        </dl>
      )}
      {o.deployment_weeks != null && (
        <p className="mt-2 flex items-center gap-1 text-[11px] text-muted">
          <Clock className="size-3" aria-hidden /> about {o.deployment_weeks} weeks to deploy
        </p>
      )}
      {o.status === 'applied' ? (
        <p className="mt-2.5 flex items-center gap-1.5 text-sm font-medium text-success">
          <CircleCheck className="size-4" aria-hidden /> Already in your plan
        </p>
      ) : (
        <>
          <button
            type="button"
            onClick={onAccept}
            disabled={disabled}
            className="mt-2.5 inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-border disabled:text-muted"
          >
            <Check className="size-4" aria-hidden /> Accept for {eur(o.cost_eur)}
          </button>
          {o.status === 'over_budget' && (
            <p className="mt-1.5 flex items-center gap-1 text-xs text-warning">
              <TriangleAlert className="size-3.5" aria-hidden /> Costs more than the budget left.
            </p>
          )}
        </>
      )}
    </li>
  )
}

export default function PointDrawer(props: Props) {
  const { point, trail, result, metric, rec, isWorst, nextWorstId, busy, solarUnit, onAccept, onClose, onGoTo } = props
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus({ preventScroll: true })
  }, [point.id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const raw = result?.raw
  const options = rec.data?.point_id === point.id ? rec.data.options : undefined
  const useful = options?.filter((o) => o.status === 'available' || o.status === 'over_budget' || o.status === 'applied') ?? []
  const noEffect = options?.filter((o) => o.status === 'no_effect') ?? []
  const bestId = options?.find((o) => o.status === 'available')?.fix_id

  return (
    <aside
      aria-label={`Details for ${pointTitle(point)}`}
      className="absolute inset-x-0 bottom-0 z-[1001] flex max-h-[70%] flex-col border-t border-border bg-surface shadow-2xl md:inset-x-auto md:right-0 md:top-0 md:max-h-none md:w-[400px] md:border-l md:border-t-0"
    >
      <div className="flex items-start gap-2 border-b border-border p-4">
        <MapPin className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded-md bg-background px-1.5 py-0.5 text-[11px] font-medium text-muted">{KIND_LABEL[point.kind]}</span>
            {isWorst && <span className="rounded-md bg-score-5 px-1.5 py-0.5 text-[11px] font-semibold text-white">Worst for {METRIC_SHORT[metric]}</span>}
          </div>
          <h2 className="mt-1 text-lg font-semibold leading-snug">{pointTitle(point)}</h2>
          <p className="text-xs text-muted">{pointSubtitle(point, trail)}</p>
        </div>
        <button ref={closeRef} type="button" onClick={onClose} aria-label="Close details" className="rounded-md p-1 text-muted hover:bg-background hover:text-foreground">
          <X className="size-5" />
        </button>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto p-4">
        {point.kind !== 'segment' && (
          <p className="flex gap-2 rounded-lg border border-warning/30 bg-warning-soft p-2.5 text-xs text-warning">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <span>
              Approximate location. This synthetic point was moved {metres(point.snap_distance_m)} onto its own trail ({point.trail_id}) so its data stays
              consistent with the street it describes.
            </span>
          </p>
        )}

        {raw && result && (
          <section aria-label="Scores at this point" className="space-y-1">
            <MetricRow
              metric="water"
              active={metric === 'water'}
              score={result.scores.water}
              detail={`${metres(raw.water_dist_m)} to the nearest drinking water`}
            />
            <MetricRow
              metric="sun"
              active={metric === 'sun'}
              score={result.scores.sun}
              detail={
                `Solar ${int(raw.solar)} ${solarUnit}` +
                (raw.wait_s != null ? ` · red light ${int(raw.wait_s)} s at ${int(raw.shade_pct)} % shade` : '')
              }
            />
            <MetricRow metric="heat" active={metric === 'heat'} score={result.scores.heat} detail={`UTCI ${celsius(raw.utci_c)} at 14:00 (synthetic)`} />
            <MetricRow metric="combined" active={metric === 'combined'} score={result.scores.combined} detail="Mean of water, sun and heat" />
          </section>
        )}

        {trail && (
          <dl className="grid grid-cols-2 gap-x-3 gap-y-2 rounded-lg bg-surface-2 p-3 text-xs">
            <div>
              <dt className="text-muted">Trail riders per day (synthetic)</dt>
              <dd className="mt-0.5 flex items-center gap-1 font-medium">
                <Users className="size-3.5 text-muted" aria-hidden />
                {int(trail.riders_spring)} spring · {int(trail.riders_summer)} summer
              </dd>
            </div>
            <div>
              <dt className="text-muted">Summer drop</dt>
              <dd className="mt-0.5 font-medium">{dec2(trail.summer_drop_pct)} %</dd>
            </div>
            {point.kind === 'segment' && (
              <div>
                <dt className="text-muted">Length of this piece</dt>
                <dd className="mt-0.5 font-medium">{metres(point.length_m)}</dd>
              </div>
            )}
            <div>
              <dt className="text-muted">Nearest climate shelter</dt>
              <dd className="mt-0.5 font-medium">{trail.nearest_shelter_name ?? trail.nearest_shelter_id}</dd>
            </div>
            {point.notes && (
              <div className="col-span-2">
                <dt className="text-muted">Note (synthetic)</dt>
                <dd className="mt-0.5">{point.notes}</dd>
              </div>
            )}
          </dl>
        )}

        <section aria-labelledby="recs-h" aria-busy={rec.loading}>
          <div className="mb-2 flex items-center justify-between">
            <h3 id="recs-h" className="text-sm font-semibold">
              Recommended fixes · {METRIC_SHORT[metric]}
            </h3>
            {rec.loading && <LoaderCircle className="size-4 animate-spin text-muted" aria-label="Loading" />}
          </div>
          {rec.error && (
            <p role="alert" className="rounded-lg bg-danger-soft p-2.5 text-xs text-danger">
              Couldn't load recommendations: {rec.error}
            </p>
          )}
          {!options && !rec.error && (
            <div className="space-y-2">
              <div className="cc-skeleton h-32" />
              <div className="cc-skeleton h-24" />
            </div>
          )}
          {options && useful.length === 0 && (
            <p className="rounded-lg border border-dashed border-border-strong p-3 text-xs text-muted">
              No catalogue fix improves {METRIC_SHORT[metric].toLowerCase()} at this point.
              {nextWorstId && ' Try the next worst point.'}
            </p>
          )}
          {useful.length > 0 && (
            <ul className="space-y-2.5">
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
      </div>

      {nextWorstId && nextWorstId !== point.id && (
        <div className="border-t border-border p-3">
          <button
            type="button"
            onClick={() => onGoTo(nextWorstId)}
            className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-primary px-3 py-2 text-sm font-semibold text-primary hover:bg-primary-soft"
          >
            Go to current worst point <ArrowRight className="size-4" aria-hidden />
          </button>
        </div>
      )}
    </aside>
  )
}
