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
 * normal-vision ΔE floor (13.5 < 15) in the dataviz validator; score-fine passes (16.9) and is the map's
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
  const strongHeat = strongHeatC == null ? '38 °C' : `${strongHeatC} °C`
  const comfort = comfortC == null ? '32 °C' : `${comfortC} °C`
  const burdenCut = burdenPct != null && burdenPct >= 0.05
  const cooled = k.utci_drop_trail_avg_c != null
  const ofNetwork = (v: number) => `${dec1(v)} / ${dec1(network_km)} km`
  return [
    {
      label: `${METRIC_SHORT[metric]} burden cut`,
      icon: METRIC_ICON[metric],
      tone: 'cool',
      value: burdenPct == null ? DASH : burdenCut ? pct(burdenPct) : '0%',
      reduction: burdenCut,
      sub: 'vs today, whole network',
      formula:
        'How much the plan lowers the burden of the selected metric, compared with today. Burden = Σ score × riders/day × seconds spent at each point (riding a piece at cycling speed, scaled to the VAS-R1 trail length; waiting at a red light, which a green wave shortens; docking at a station).',
      emphasis: true,
    },
    {
      label: 'Comfortable km',
      icon: KPI_ICON.comfort,
      tone: 'cool',
      ...coverage(comfortable_km, k.comfortable_km_gain, network_km, 'cool', 'comfortable'),
      sub: `${ofNetwork(comfortable_km)} · warm day`,
      formula: `Share of the network's length with UTCI below ${comfort} (no more than moderate heat stress) on a warm summer afternoon (60th–80th percentile July–August days, ~29 °C air). Fixes keep their catalogue UTCI cut.`,
    },
    {
      label: `Below ${strongHeat}, heatwave`,
      icon: KPI_ICON.heatStress,
      tone: 'cool',
      ...coverage(below_strong_heat_km, strongHeatGain, network_km, 'cool', `below ${strongHeat}`),
      sub: ofNetwork(below_strong_heat_km),
      formula: `Share of the network's length with UTCI below ${strongHeat} (out of "very strong heat stress") on a peak heatwave afternoon (2 hottest July–August days of 2023–2025, ~34 °C air). Fixes keep their catalogue UTCI cut.`,
    },
    {
      label: waterReachM == null ? 'Water nearby' : `Water ≤ ${waterReachM} m`,
      icon: KPI_ICON.water,
      tone: 'water',
      ...coverage(water_reachable_km, waterGain, network_km, 'water', 'with water nearby'),
      sub: ofNetwork(water_reachable_km),
      formula: `A street piece counts if any part is within ${waterDistance} of a drinking fountain or cyclist oasis in a straight line.`,
    },
    {
      label: 'Critical points',
      icon: KPI_ICON.cooling,
      tone: 'cool',
      value: celsius(k.critical_drop_avg_c ?? 0),
      reduction: (k.critical_drop_avg_c ?? 0) > 0,
      sub:
        k.critical_drop_max_c != null
          ? `${k.critical_cooled} of ${k.critical_total} cooled · max ${celsius(k.critical_drop_max_c)}`
          : `0 of ${k.critical_total} cooled`,
      formula:
        'Average modelled UTCI drop over ALL critical points (uncooled ones count 0): the 5 traffic-light junctions plus the street pieces and stations in the hottest 10% of today’s computed UTCI. Several fixes at one place combine with a discount. A green wave shortens the wait instead of lowering UTCI, so it does not show here.' +
        (k.critical_drop_cooled_avg_c != null ? ` Where cooled: ${celsius(k.critical_drop_cooled_avg_c)} on average.` : '') +
        (cooled ? ` Over all cooled street pieces: ${celsius(k.utci_drop_trail_avg_c)} on ${km(k.utci_cooled_trail_km)}.` : ''),
    },
    {
      label: 'CO₂ from car trips',
      icon: KPI_ICON.co2,
      tone: 'neutral',
      value: `${k.co2_trips_t_per_year > 0 ? '+' : ''}${dec2(k.co2_trips_t_per_year)} t/yr`,
      sub: `+${dec2(k.co2_sequestration_t_per_year)} t trees · +${dec2(k.co2_pv_avoided_t_per_year)} t solar`,
      formula:
        `Replaced trips: recovered trips/day × share that replace a car × kg CO₂ per car trip (INT-08) × summer days. Shown separately below: CO₂ captured by trees and oasis greenery, and CO₂ avoided by the solar power of station canopies (total ${dec2(k.co2_t_per_year)} t/yr).`,
    },
  ]
}

function GainBadge({ pp, hasPlan }: { pp: number; hasPlan: boolean }) {
  if (!hasPlan) return null
  if (pp < 0.05) return <span className="whitespace-nowrap text-xs font-medium text-muted">no change</span>
  return (
    <span className="whitespace-nowrap text-xs font-bold text-gain" title="Change since today in percentage points">
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
    <li className={`grid min-w-[170px] flex-1 grid-cols-[auto_1fr] content-start items-center gap-x-2 px-3 py-2.5 ${t.emphasis ? 'bg-primary-soft' : 'bg-surface'}`}>
      {/* Label on its own full-width row above the icon, so it has room and doesn't get cut. */}
      <p className="col-span-2 mb-1.5 flex min-w-0 items-center gap-1 text-[11px] font-medium leading-tight text-muted">
        <span className="truncate" title={t.label}>{t.label}</span>
        <span title={t.formula} className="shrink-0 cursor-help" aria-label={`How it is calculated: ${t.formula}`}>
          <Info className="size-3" aria-hidden />
        </span>
      </p>
      <span
        className={`grid size-7 place-items-center rounded-lg ${t.emphasis ? 'bg-primary text-primary-foreground' : CHIP[t.tone]}`}
        aria-hidden
      >
        <Icon className="size-3.5" />
      </span>
      <p className="flex min-w-0 flex-wrap items-center gap-x-2 leading-tight">
        <span className={`flex items-center gap-0.5 text-base font-semibold ${t.emphasis ? 'text-primary' : 'text-foreground'}`}>
          {t.reduction && <ArrowDown className="size-4 text-gain" strokeWidth={2.5} aria-hidden />}
          {t.value}
        </span>
        {t.gainPp != null && <GainBadge pp={t.gainPp} hasPlan={hasPlan} />}
      </p>
      {/* Tiles without a bar keep its space so every sub-line sits on the same row. */}
      {t.bar ? <TrailBar bar={t.bar} /> : <div className="col-span-2 mt-2 h-1" aria-hidden />}
      {t.sub && (
        <p className="col-span-2 mt-1 min-w-0 truncate text-[11px] text-muted" title={t.sub}>
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
              <li key={i} className="min-w-[170px] flex-1 bg-surface px-3 py-2.5">
                <div className="cc-skeleton h-3 w-20" />
                <div className="mt-2 flex items-center gap-2">
                  <div className="cc-skeleton size-7 rounded-lg" />
                  <div className="cc-skeleton h-5 w-16" />
                </div>
              </li>
            ))}
      </ul>
    </section>
  )
}

// Memoised: the page re-renders on every hover over the worst list; the KPIs only change with the evaluation.
export default memo(KpiStrip)
