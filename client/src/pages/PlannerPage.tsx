import { RefreshCw, TriangleAlert, X } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import type { PointKind } from '../api/planner.ts'
import AppHeader from '../components/AppHeader.tsx'
import AssumptionsModal from '../components/AssumptionsModal.tsx'
import BudgetPanel from '../components/BudgetPanel.tsx'
import KpiStrip from '../components/KpiStrip.tsx'
import MapView from '../components/MapView.tsx'
import MetricPicker from '../components/MetricPicker.tsx'
import PlanList from '../components/PlanList.tsx'
import PointDrawer from '../components/PointDrawer.tsx'
import PointTypeFilter from '../components/PointTypeFilter.tsx'
import RecommendedFixes from '../components/RecommendedFixes.tsx'
import WorstList from '../components/WorstList.tsx'
import { POINT_KINDS, rankWorst } from '../lib/points.ts'
import { useMediaQuery } from '../lib/useMediaQuery.ts'
import { usePlanner } from '../lib/usePlanner.ts'

/**
 * Tailwind's `lg` width, so this switches together with the `lg:` classes below. From here the point details
 * open in a popup above the point on the map, and "Your plan", with the selected point's recommended fixes
 * under it, gets its own column right of the map. On smaller screens the details cover the map with the fixes
 * inside, and the plan stays under the list.
 */
const WIDE = '(min-width: 64rem)'

function SidebarSkeleton() {
  return (
    <div className="space-y-6 p-4" aria-hidden>
      <div className="cc-skeleton h-20" />
      <div className="cc-skeleton h-16" />
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="cc-skeleton h-11" />
      ))}
    </div>
  )
}

export default function PlannerPage() {
  const pl = usePlanner()
  const [hoveredId, setHoveredId] = useState<string>()
  const [assumptionsOpen, setAssumptionsOpen] = useState(false)
  const wide = useMediaQuery(WIDE)
  const data = pl.mapData.data
  const ev = pl.evaluation
  const { setSelectedId } = pl
  const close = useCallback(() => setSelectedId(undefined), [setSelectedId])
  // Bumped on every pick, so the map flies to the point even when the same one is picked again.
  const [focusRequest, setFocusRequest] = useState(0)
  const select = useCallback(
    (id: string) => {
      setSelectedId(id)
      setFocusRequest((n) => n + 1)
    },
    [setSelectedId],
  )

  // "Where to look": which point kinds are in play. It narrows the worst list and so decides the worst point, and
  // the map greys out the other kinds. All on by default.
  const [kinds, setKinds] = useState<Set<PointKind>>(() => new Set(POINT_KINDS))
  // Ranked here, not taken from the server's `worst`, which ignores the filter (and stops at 10).
  const ranked = useMemo(() => (ev ? rankWorst(ev.points, pl.pointsById, kinds) : []), [ev, pl.pointsById, kinds])
  const kindCounts = useMemo(() => {
    const counts: Record<PointKind, number> = { segment: 0, junction: 0, station: 0 }
    for (const r of ev?.points ?? []) {
      const kind = pl.pointsById.get(r.id)?.kind
      if (r.priority > 0 && kind) counts[kind] += 1
    }
    return counts
  }, [ev?.points, pl.pointsById])

  const selected = pl.selectedId ? pl.pointsById.get(pl.selectedId) : undefined
  const worstId = ranked[0]
  const solarUnit = String(data?.assumptions.find((a) => a.key === 'solar_unit')?.value ?? '')
  const waterReachM = data?.assumptions.find((a) => a.key === 'water_ok_m')?.value
  const strongHeatC = data?.assumptions.find((a) => a.key === 'strong_heat_utci_c')?.value

  // These are placed in one of two spots below, depending on the screen width.
  const fixes = data && selected && (
    <RecommendedFixes
      point={selected}
      metric={ev?.metric ?? pl.metric}
      rec={pl.recommendation}
      nextWorstId={worstId}
      busy={pl.evaluating}
      onAccept={(fixId) => pl.accept(fixId, selected.id)}
    />
  )
  const details = data && selected && (
    <PointDrawer
      key={selected.id}
      placement={wide ? 'popup' : 'overlay'}
      point={selected}
      trail={pl.trailsById.get(selected.trail_id)}
      result={pl.resultsById.get(selected.id)}
      metric={ev?.metric ?? pl.metric}
      isWorst={selected.id === worstId}
      solarUnit={solarUnit}
      onClose={close}
    >
      {!wide && fixes}
    </PointDrawer>
  )
  const plan = ev && (
    <PlanList
      plan={ev.plan}
      pointsById={pl.pointsById}
      selectedId={pl.selectedId}
      revealSelected={wide}
      onRemove={pl.remove}
      onUndo={pl.undo}
      onReset={pl.reset}
      onSelect={select}
      busy={pl.evaluating}
    />
  )

  return (
    <>
      <AppHeader onOpenAssumptions={() => setAssumptionsOpen(true)} assumptionsDisabled={!data} />

      {pl.mapData.error ? (
        <div className="grid flex-1 place-items-center p-6">
          <div role="alert" className="max-w-md rounded-2xl border border-danger/30 bg-surface p-6 text-center shadow-sm">
            <TriangleAlert className="mx-auto size-8 text-danger" aria-hidden />
            <h1 className="mt-2 text-lg font-semibold">Couldn't load the trail data</h1>
            <p className="mt-1 text-sm text-muted">{pl.mapData.error}. Is the backend running on port 8000?</p>
            <button
              type="button"
              onClick={pl.retryMapData}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary-hover"
            >
              <RefreshCw className="size-4" aria-hidden /> Try again
            </button>
          </div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          <aside
            aria-label="Planner controls"
            className="max-h-[45vh] shrink-0 overflow-y-auto border-b border-border bg-surface lg:max-h-none lg:w-[320px] lg:border-b-0 lg:border-r"
          >
            {!data || !ev ? (
              <SidebarSkeleton />
            ) : (
              <div className="space-y-6 p-4">
                <BudgetPanel key={ev.budget.total} budget={ev.budget.total} spent={ev.budget.spent} onChange={pl.setBudget} />
                <MetricPicker metrics={data.metrics} value={pl.metric} onChange={pl.setMetric} />
                <PointTypeFilter value={kinds} counts={kindCounts} onChange={setKinds} />
                <WorstList
                  metric={ev.metric}
                  ranked={ranked}
                  pointsById={pl.pointsById}
                  resultsById={pl.resultsById}
                  kinds={kinds}
                  selectedId={pl.selectedId}
                  onSelect={select}
                  onHover={setHoveredId}
                />
                {!wide && plan}
              </div>
            )}
          </aside>

          <main className="relative flex min-h-[420px] min-w-0 flex-1 flex-col">
            <div className="flex min-h-0 flex-1">
              <div className="relative min-w-0 flex-1">
                {data ? (
                  <MapView
                    mapData={data}
                    evaluation={ev}
                    metric={ev?.metric ?? pl.metric}
                    kinds={kinds}
                    worstId={worstId}
                    selectedId={pl.selectedId}
                    hoveredId={hoveredId}
                    onSelect={select}
                    focusRequest={focusRequest}
                    drawerOverMap={!!selected && !wide}
                    popup={wide && details}
                    onClosePopup={close}
                  />
                ) : (
                  <div className="cc-skeleton h-full w-full rounded-none" aria-label="Loading map" />
                )}

                {(pl.notice || pl.evalError) && (
                  <div
                    role="alert"
                    className="absolute left-1/2 top-14 z-[1002] flex max-w-[90%] -translate-x-1/2 items-start gap-2 rounded-xl border border-danger/30 bg-surface px-3 py-2 text-sm shadow-lg"
                  >
                    <TriangleAlert className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
                    <span>{pl.notice ?? `Couldn't update the plan: ${pl.evalError}`}</span>
                    {pl.notice && (
                      <button type="button" onClick={pl.dismissNotice} aria-label="Dismiss" className="text-muted hover:text-foreground">
                        <X className="size-4" />
                      </button>
                    )}
                  </div>
                )}

                {!wide && details}
              </div>

              {wide && (
                <aside aria-label="Your plan" className="w-[300px] shrink-0 xl:w-[340px] overflow-y-auto border-l border-border bg-surface p-4">
                  {plan ?? (
                    <div className="space-y-2.5" aria-hidden>
                      <div className="cc-skeleton h-5 w-32" />
                      <div className="cc-skeleton h-16" />
                    </div>
                  )}
                  {fixes && <div className="mt-6 border-t border-border pt-5">{fixes}</div>}
                </aside>
              )}
            </div>
            <KpiStrip
              kpis={ev?.kpis}
              burdenPct={ev?.burden.reduction_pct ?? null}
              metric={ev?.metric ?? pl.metric}
              fixCount={ev?.plan.length ?? 0}
              waterReachM={typeof waterReachM === 'number' ? waterReachM : undefined}
              strongHeatC={typeof strongHeatC === 'number' ? strongHeatC : undefined}
            />
          </main>
        </div>
      )}

      {data && <AssumptionsModal open={assumptionsOpen} onClose={() => setAssumptionsOpen(false)} data={data} />}
    </>
  )
}
