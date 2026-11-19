import { X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { MapData } from '../api/planner.ts'
import { eur } from '../lib/format.ts'

const SOURCE_STYLE: Record<string, string> = {
  catalogue: 'bg-primary-soft text-primary',
  'VAS-R1 data': 'bg-warning-soft text-warning',
  standard: 'bg-water-soft text-water',
  'team assumption': 'bg-background text-muted ring-1 ring-border',
}

const fmtValue = (v: number | string | string[], unit: string) =>
  Array.isArray(v) ? v.join(', ') : unit === 'share' && typeof v === 'number' ? `${Math.round(v * 100)} %` : `${v} ${unit}`.trim()

export default function AssumptionsModal({ open, onClose, data }: { open: boolean; onClose: () => void; data: MapData }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  const trailKm = data.trails.reduce((s, t) => s + t.real_length_m, 0) / 1000
  const stationCount = data.points.filter((p) => p.kind === 'station').length

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-labelledby="assumptions-h"
      className="m-auto max-h-[85vh] w-[min(860px,94vw)] rounded-2xl bg-surface p-0 text-foreground shadow-2xl"
    >
      <div className="sticky top-0 flex items-center justify-between border-b border-border bg-surface px-5 py-3">
        <h2 id="assumptions-h" className="text-lg font-semibold">
          Data & assumptions
        </h2>
        <button type="button" onClick={onClose} aria-label="Close" className="rounded-md p-1 text-muted hover:bg-background hover:text-foreground">
          <X className="size-5" />
        </button>
      </div>
      <div className="space-y-6 px-5 py-4 text-sm">
        <section>
          <h3 className="mb-2 font-semibold">Where the numbers come from</h3>
          <ul className="space-y-1.5 text-muted">
            <li>
              <strong className="text-foreground">Real municipal data:</strong> street geometry of the cycle network, the solar value of each street segment,{' '}
              {data.fountains.length} drinking fountains (cemetery fountains excluded) and {stationCount} AMBici bike stations.
            </li>
            <li>
              <strong className="text-foreground">Synthetic VAS-R1 data:</strong> UTCI heat stress, junctions, the extra heat at two bike stations and the fix
              catalogue. Never read them as measured Viladecans values.
            </li>
            <li>
              <strong className="text-foreground">Scope:</strong> {data.trails.length} VAS-R1 trails mapped onto real streets by name ({trailKm.toFixed(1)} km). The
              Agrarian Path has no matching street and is left out. Junctions are placed on their own trail (approximate location). Bike stations are at their
              real location, also off the trails, and take the heat of the nearest trail.
            </li>
          </ul>
        </section>

        <section>
          <h3 className="mb-2 font-semibold">Assumptions</h3>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-2 text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Assumption</th>
                  <th className="px-3 py-2 font-medium">Value</th>
                  <th className="px-3 py-2 font-medium">Source</th>
                  <th className="px-3 py-2 font-medium">Why</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.assumptions.map((a) => (
                  <tr key={a.key}>
                    <td className="px-3 py-2 font-medium">{a.label}</td>
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                      {fmtValue(a.value, a.unit)}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ${SOURCE_STYLE[a.source] ?? ''}`}>{a.source}</span>
                    </td>
                    <td className="px-3 py-2 text-muted">{a.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h3 className="mb-2 font-semibold">Fix catalogue (VAS-R1, synthetic)</h3>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-2 text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Fix</th>
                  <th className="px-3 py-2 font-medium">Placed on</th>
                  <th className="px-3 py-2 font-medium">Cost</th>
                  <th className="px-3 py-2 font-medium">Effects used by the model</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.catalogue.map((c) => (
                  <tr key={c.id}>
                    <td className="px-3 py-2">
                      <span className="font-medium">{c.label}</span> <span className="text-muted">({c.id})</span>
                      <p className="text-muted">{c.description}</p>
                    </td>
                    <td className="px-3 py-2">{c.allowed_on.join(', ')}</td>
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                      {eur(c.capex_eur)} {c.priced_per_m ? '/ 100 m' : ''}
                      <p className="text-muted">+ {eur(c.opex_eur_yr)}/yr</p>
                    </td>
                    <td className="px-3 py-2 text-muted">{c.effects.join(' · ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted">Not used: INT-07 (city-wide app, no location) and INT-08 (modal-shift factors per replaced trip; we have no ridership data to apply them to).</p>
        </section>
      </div>
    </dialog>
  )
}
