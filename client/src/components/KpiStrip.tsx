import { ArrowDown, Info, type LucideIcon } from 'lucide-react'
import { memo } from 'react'
import type { Kpis, MetricId } from '../api/planner.ts'
import { celsius, DASH, dec1, dec2, km } from '../lib/format.ts'
import { KPI_ICON, METRIC_ICON, METRIC_SHORT } from '../lib/icons.tsx'

/*
 * Colour roles in the strip:
 *  - chip tone = what the tile is about (cool/shade = teal, water = blue, CO₂ = neutral);
 *  - green (gain) = what the plan added, in both the badges and the bars.
 * Bar baselines use score-fine (not the brand teal) because brand teal next to gain green failed the
 * normal-vision ΔE floor (13.5 < 15) in the dataviz validator; score-fine passes (16.5) and is the map's
 * "fine" colour, which is what "comfortable" means. The 2px surface gap between parts is the backup cue.
 */
type Tone = 'cool' | 'water' | 'neutral'
type BarTone = Exclude<Tone, 'neutral'>

const CHIP: Record<Tone, string> = {
  cool: 'bg-primary-soft text-primary',
  water: 'bg-water-soft text-water',
  neutral: 'bg-background text-muted',
}
const BAR: Record<BarTone, { track: string; base: string }> = {
  cool: { track: 'bg-primary-soft', base: 'bg-score-fine' },
  water: { track: 'bg-water-soft', base: 'bg-water' },
}

/** One trail-length share: the part that was already there today plus the part the plan added. */
type Bar = { baseKm: number; gainKm: number; totalKm: number; label: string; tone: BarTone }

type Tile = {
  label: string
  icon: LucideIcon
  tone: Tone
  value: string
  /** The value is itself a reduction (burden, UTCI): shown with a green down arrow. */
  reduction?: boolean
  /** Change of a coverage share since today, in percentage points. */
  gainPp?: number
  bar?: Bar
  sub?: string
  formula: string
  emphasis?: boolean
}

type Props = {
  kpis?: Kpis
  burdenPct: number | null
  metric: MetricId
  fixCount: number
  waterReachM?: number
  strongHeatC?: number
  comfortC?: number
}

const pct = (v: number) => `${dec1(v)}%`
const share = (part: number, total: number) => (total > 0 ? (part / total) * 100 : 0)

function coverage(afterKm: number, gainKm: number, totalKm: number, tone: BarTone, what: string) {
  const gain = Math.max(0, gainKm)
  const base = Math.max(0, afterKm - gain)
  return {
    value: totalKm > 0 ? pct(share(afterKm, totalKm)) : DASH,
    gainPp: totalKm > 0 ? share(gain, totalKm) : undefined,
    bar: {
      baseKm: base,
      gainKm: gain,
      totalKm,
      tone,
      label: `${km(afterKm)} of ${km(totalKm)} ${what}: ${km(base)} today, ${km(gain)} added by the plan`,
    },
  }
}

function tiles(k: Kpis, burdenPct: number | null, metric: MetricId, waterReachM?: number, strongHeatC?: number, comfortC?: number): Tile[] {
  const { comfortable_km, below_strong_heat_km, network_km, water_reachable_km } = k.after
  const waterGain = water_reachable_km - k.before.water_reachable_km
  const strongHeatGain = below_strong_heat_km - k.before.below_strong_heat_km
  const waterDistance = waterReachM == null ? 'the configured distance' : `${waterReachM} m`
  const strongHeat = strongHeatC == null ? 'the very strong heat threshold' : `${strongHeatC} °C`
  const comfort = comfortC == null ? 'the comfort threshold' : `${comfortC} °C`
  const burdenCut = burdenPct != null && burdenPct >= 0.05
  const cooled = k.utci_drop_trail_avg_c != null
  return [
    {
      label: `${METRIC_SHORT[metric]} burden reduced`,
      icon: METRIC_ICON[metric],
      tone: 'cool',
      value: burdenPct == null ? DASH : burdenCut ? pct(burdenPct) : '0%',
      reduction: burdenCut,
      sub: "of today's total, whole trail network",
      formula:
        'How much the plan lowers the burden of the selected metric, compared with today. Burden = Σ score × riders/day × seconds spent at each point (riding a piece at cycling speed, scaled to the VAS-R1 trail length; waiting at a red light, which a green wave shortens; docking at a station).',
      emphasis: true,
    },
    {
      label: 'Comfortable trail length',
      icon: KPI_ICON.comfort,
      tone: 'cool',
      ...coverage(comfortable_km, k.comfortable_km_gain, network_km, 'cool', 'comfortable'),
      sub: `${dec2(comfortable_km)} / ${km(network_km)} of network`,
      formula: `Share of the whole network's length with UTCI below ${comfort} on a hot summer afternoon (computed from real weather, local sun and ground temperature).`,
    },
    {
      label: 'Out of very strong heat',
      icon: KPI_ICON.heatStress,
      tone: 'cool',
      ...coverage(below_strong_heat_km, strongHeatGain, network_km, 'cool', `below ${strongHeat}`),
      sub: `${dec2(below_strong_heat_km)} / ${km(network_km)} · UTCI below ${strongHeat}`,
      formula: `Share of the whole network's length with UTCI below ${strongHeat}: at most "strong heat stress", out of the "very strong heat stress" band.`,
    },
    {
      label: 'Drinking water nearby',
      icon: KPI_ICON.water,
      tone: 'water',
      ...coverage(water_reachable_km, waterGain, network_km, 'water', 'with water nearby'),
      sub: `${dec2(water_reachable_km)} / ${km(network_km)} · within ${waterDistance}`,
      formula: `A street piece counts if any part is within ${waterDistance} of a drinking fountain or cyclist oasis in a straight line.`,
    },
    {
      label: '°C at critical points',
      icon: KPI_ICON.cooling,
      tone: 'cool',
      value: celsius(k.critical_drop_avg_c),
      reduction: k.critical_drop_avg_c != null,
      sub:
        k.critical_drop_max_c != null
          ? `${celsius(k.critical_drop_cooled_avg_c)} where cooled, max ${celsius(k.critical_drop_max_c)} · ${k.critical_cooled} of ${k.critical_total} critical points`
          : `none of ${k.critical_total} critical points cooled yet`,
      formula:
        'Average modelled UTCI drop over ALL critical points (uncooled ones count 0): the 5 traffic-light junctions and every point on a trail rated "Critical" in the VAS-R1 data. Several fixes at one place combine with a discount (assumptions are listed in the PDF report). A green wave shortens the wait instead of lowering UTCI, so it does not show here.' +
        (cooled ? ` Over all cooled street pieces: ${celsius(k.utci_drop_trail_avg_c)} on ${km(k.utci_cooled_trail_km)}.` : ''),
    },
    {
      label: 'CO₂ avoided',
      icon: KPI_ICON.co2,
      tone: 'neutral',
      value: `${k.co2_t_per_year > 0 ? '+' : ''}${dec2(k.co2_t_per_year)} t/yr`,
      sub: `${dec2(k.co2_trips_t_per_year)} t replaced car trips · ${dec2(k.co2_sequestration_t_per_year)} t trees & oases · ${dec2(k.co2_pv_avoided_t_per_year)} t solar canopies`,
      formula:
        'Replaced trips: recovered trips/day × share that replace a car × kg CO₂ per car trip (INT-08) × summer days. Plus CO₂ captured by trees and oasis greenery, and CO₂ avoided by the solar power of station canopies (shown separately).',
    },
  ]
}

function GainBadge({ pp, hasPlan }: { pp: number; hasPlan: boolean }) {
  if (!hasPlan) return null
  if (pp < 0.05) return <span className="whitespace-nowrap text-xs font-medium text-muted">no change</span>
  return (
    <span className="whitespace-nowrap rounded-full bg-gain-soft px-1.5 py-px text-xs font-bold text-gain" title="Change since today in percentage points">
      +{dec1(pp)} <span aria-hidden="true">pp</span>
      <span className="sr-only">percentage points since today</span>
    </span>
  )
}

function TrailBar({ bar }: { bar: Bar }) {
  const base = Math.min(100, share(bar.baseKm, bar.totalKm))
  const gain = Math.min(100, share(bar.gainKm, bar.totalKm))
  const { track, base: baseFill } = BAR[bar.tone]
  return (
    <div role="img" aria-label={bar.label} title={bar.label} className={`col-span-2 mt-2 flex h-1 overflow-hidden rounded-full ${track}`}>
      {base > 0 && <div className={`h-full rounded-full ${baseFill}`} style={{ width: `${base}%` }} />}
      {gain > 0 && (
        // A tiny gain still gets a visible sliver; the white left border is the 2px gap between parts.
        <div
          className={`h-full shrink-0 rounded-full bg-gain ${base > 0 ? 'border-l-2 border-surface' : ''}`}
          style={{ width: `${gain}%`, minWidth: base > 0 ? 6 : 4 }}
        />
      )}
    </div>
  )
}

function TileView({ t, hasPlan }: { t: Tile; hasPlan: boolean }) {
  const Icon = t.icon
  return (
    <li className={`grid min-w-[180px] flex-1 grid-cols-[auto_1fr] content-start gap-x-2.5 px-3 py-2.5 ${t.emphasis ? 'bg-primary-soft' : 'bg-surface'}`}>
      <span
        className={`row-span-2 grid size-8 place-items-center self-center rounded-lg ${t.emphasis ? 'bg-primary text-primary-foreground' : CHIP[t.tone]}`}
        aria-hidden
      >
        <Icon className="size-4" />
      </span>
      <p className="flex min-w-0 items-center gap-1 text-[11px] font-medium text-muted">
        <span className="truncate">{t.label}</span>
        <span title={t.formula} className="shrink-0 cursor-help" aria-label={`How it is calculated: ${t.formula}`}>
          <Info className="size-3" aria-hidden />
        </span>
      </p>
      <p className="flex items-center gap-2 leading-tight">
        <span className={`flex items-center gap-0.5 text-lg font-semibold ${t.emphasis ? 'text-primary' : 'text-foreground'}`}>
          {t.reduction && <ArrowDown className="size-4 text-gain" strokeWidth={2.5} aria-hidden />}
          {t.value}
        </span>
        {t.gainPp != null && <GainBadge pp={t.gainPp} hasPlan={hasPlan} />}
      </p>
      {/* Tiles without a bar keep its space so every sub-line sits on the same row. */}
      {t.bar ? <TrailBar bar={t.bar} /> : <div className="col-span-2 mt-2 h-1" aria-hidden />}
      {t.sub && (
        <p className="col-span-2 mt-1 text-[11px] text-muted" title={t.sub}>
          {t.sub}
        </p>
      )}
    </li>
  )
}

function KpiStrip({ kpis, burdenPct, metric, fixCount, waterReachM, strongHeatC, comfortC }: Props) {
  const hasPlan = fixCount > 0
  return (
    <section aria-label="Impact of your plan vs today" className="shrink-0 border-t border-border bg-surface">
      <ul className="flex gap-px overflow-x-auto bg-border">
        {kpis
          ? tiles(kpis, burdenPct, metric, waterReachM, strongHeatC, comfortC).map((t) => <TileView key={t.label} t={t} hasPlan={hasPlan} />)
          : Array.from({ length: 6 }, (_, i) => (
              <li key={i} className="flex min-w-[180px] flex-1 items-center gap-2.5 bg-surface px-3 py-2.5">
                <div className="cc-skeleton size-8 rounded-lg" />
                <div>
                  <div className="cc-skeleton h-3 w-20" />
                  <div className="cc-skeleton mt-2 h-5 w-16" />
                </div>
              </li>
            ))}
      </ul>
    </section>
  )
}

// Memoised: the page re-renders on every hover over the worst list; the KPIs only change with the evaluation.
export default memo(KpiStrip)
