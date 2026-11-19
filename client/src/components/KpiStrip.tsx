import { Info } from 'lucide-react'
import type { Kpis } from '../api/planner.ts'
import { celsius, dec1, dec2, eur, int, km } from '../lib/format.ts'

type Tile = { label: string; value: string; sub?: string; formula: string; emphasis?: boolean }

function tiles(k: Kpis, burdenPct: number | null, metricLabel: string): Tile[] {
  const gain = k.comfortable_km_gain
  const waterGain = k.after.water_reachable_km - k.before.water_reachable_km
  return [
    {
      label: `${metricLabel} burden`,
      value: burdenPct == null ? '—' : burdenPct < 0.05 ? '0 %' : `−${dec1(burdenPct)} %`,
      sub: 'vs today, whole trail network',
      formula: 'Reduction of Σ (score × spring riders × length) over all trail points for the selected metric.',
      emphasis: true,
    },
    {
      label: 'Comfortable km',
      value: km(k.after.comfortable_km),
      sub: gain > 0 ? `+${dec2(gain)} km · was ${km(k.before.comfortable_km)}` : `of ${km(k.after.trail_km)} trails`,
      formula: 'Length of trail pieces with UTCI below the comfort threshold (see Data & assumptions).',
    },
    {
      label: 'Water within reach',
      value: km(k.after.water_reachable_km),
      sub: waterGain > 0 ? `+${dec2(waterGain)} km · was ${km(k.before.water_reachable_km)}` : `of ${km(k.after.trail_km)} trails`,
      formula: 'Length of trail pieces with a fountain or oasis within the short-detour distance.',
    },
    {
      label: 'UTCI drop at fixed points',
      value: k.utci_drop_avg_c == null ? '—' : celsius(k.utci_drop_avg_c),
      sub: k.utci_drop_max_c == null ? 'no point cooled yet' : `max ${celsius(k.utci_drop_max_c)} · ${k.points_cooled} ${k.points_cooled === 1 ? 'point' : 'points'}`,
      formula: 'Average and maximum UTCI reduction over all points whose UTCI went down.',
    },
    {
      label: 'New summer cyclists',
      value: int(k.new_summer_cyclists),
      sub: `${int(k.recovered_trips_per_day)} trips/day won back`,
      formula:
        'Per trail: summer ridership drop × share of the UTCI gap to the cool benchmark trails closed. Rider-km ÷ average trip length = trips; trips ÷ trips per cyclist = cyclists.',
    },
    {
      label: 'CO₂ avoided',
      value: `${dec2(k.co2_t_per_year)} t/yr`,
      sub: `${dec2(k.co2_from_trips_t)} t trips · ${dec2(k.co2_from_sequestration_t)} t trees & canopies`,
      formula: 'Trips × CO₂ per replaced car trip × summer days, plus catalogue CO₂ sequestration/avoidance of the fixes.',
    },
    {
      label: '€ per comfortable km',
      value: eur(k.eur_per_comfortable_km),
      sub: `plan ${eur(k.capex_eur)} + ${eur(k.opex_eur_per_year)}/yr upkeep`,
      formula: 'Plan CAPEX ÷ km that became comfortable. "—" until at least one km gains comfort.',
    },
    {
      label: '€ per new cyclist',
      value: eur(k.eur_per_new_cyclist),
      sub: `each saves ${eur(k.eur_saved_per_cyclist_year)}/yr`,
      formula: 'Plan CAPEX ÷ new summer cyclists. Savings: trips per day × € per replaced trip × summer days.',
    },
  ]
}

export default function KpiStrip({ kpis, burdenPct, metricLabel }: { kpis?: Kpis; burdenPct: number | null; metricLabel: string }) {
  return (
    <section aria-label="Impact of the plan" className="shrink-0 border-t border-border bg-surface">
      <ul className="flex gap-px overflow-x-auto bg-border">
        {kpis
          ? tiles(kpis, burdenPct, metricLabel).map((t) => (
              <li key={t.label} className={`min-w-[150px] flex-1 px-3 py-2.5 ${t.emphasis ? 'bg-primary-soft' : 'bg-surface'}`}>
                <p className="flex items-center gap-1 text-[11px] font-medium text-muted">
                  {t.label}
                  <span title={t.formula} className="cursor-help" aria-label={`How it is calculated: ${t.formula}`}>
                    <Info className="size-3" aria-hidden />
                  </span>
                </p>
                <p className={`mt-0.5 text-lg font-semibold tabular-nums leading-tight ${t.emphasis ? 'text-primary' : ''}`}>{t.value}</p>
                {t.sub && <p className="truncate text-[11px] text-muted" title={t.sub}>{t.sub}</p>}
              </li>
            ))
          : Array.from({ length: 8 }, (_, i) => (
              <li key={i} className="min-w-[150px] flex-1 bg-surface px-3 py-2.5">
                <div className="cc-skeleton h-3 w-20" />
                <div className="cc-skeleton mt-2 h-5 w-16" />
              </li>
            ))}
      </ul>
    </section>
  )
}
