import { MousePointerClick, RefreshCw, TriangleAlert, X } from 'lucide-react'
import { useCallback, useState } from 'react'
import AppHeader from '../components/AppHeader.tsx'
import AssumptionsModal from '../components/AssumptionsModal.tsx'
import BudgetPanel from '../components/BudgetPanel.tsx'
import KpiStrip from '../components/KpiStrip.tsx'
import MapView from '../components/MapView.tsx'
import MetricPicker from '../components/MetricPicker.tsx'
import PlanList from '../components/PlanList.tsx'
import PointDrawer from '../components/PointDrawer.tsx'
import WorstList from '../components/WorstList.tsx'
import { METRIC_SHORT } from '../lib/icons.tsx'
import { usePlanner } from '../lib/usePlanner.ts'

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
  const data = pl.mapData.data
  const ev = pl.evaluation
  const { setSelectedId } = pl
  const close = useCallback(() => setSelectedId(undefined), [setSelectedId])

  const selected = pl.selectedId ? pl.pointsById.get(pl.selectedId) : undefined
  const worstId = ev?.worst[0]
  const solarUnit = String(data?.assumptions.find((a) => a.key === 'solar_unit')?.value ?? '')

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
            className="max-h-[45vh] shrink-0 overflow-y-auto border-b border-border bg-surface lg:max-h-none lg:w-[360px] lg:border-b-0 lg:border-r"
          >
            {!data || !ev ? (
              <SidebarSkeleton />
            ) : (
              <div className="space-y-6 p-4">
                <BudgetPanel key={ev.budget.total} budget={ev.budget.total} spent={ev.budget.spent} onChange={pl.setBudget} />
                <MetricPicker metrics={data.metrics} value={pl.metric} onChange={pl.setMetric} />
                <WorstList
                  metric={ev.metric}
                  worst={ev.worst}
                  pointsById={pl.pointsById}
                  resultsById={pl.resultsById}
                  selectedId={pl.selectedId}
                  onSelect={pl.setSelectedId}
                  onHover={setHoveredId}
                />
                <PlanList plan={ev.plan} pointsById={pl.pointsById} onUndo={pl.undo} onReset={pl.reset} onSelect={pl.setSelectedId} busy={pl.evaluating} />
              </div>
            )}
          </aside>

          <main className="relative flex min-h-[420px] min-w-0 flex-1 flex-col">
            <div className="relative min-h-0 flex-1">
              {data ? (
                <MapView
                  mapData={data}
                  evaluation={ev}
                  metric={ev?.metric ?? pl.metric}
                  selectedId={pl.selectedId}
                  hoveredId={hoveredId}
                  onSelect={pl.setSelectedId}
                  drawerOpen={!!selected}
                />
              ) : (
                <div className="cc-skeleton h-full w-full rounded-none" aria-label="Loading map" />
              )}

              {(pl.notice || pl.evalError) && (
                <div
                  role="alert"
                  className="absolute left-1/2 top-3 z-[1002] flex max-w-[90%] -translate-x-1/2 items-start gap-2 rounded-xl border border-danger/30 bg-surface px-3 py-2 text-sm shadow-lg"
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

              {data && ev && !selected && worstId && (
                <div className="pointer-events-none absolute left-3 top-3 z-[1000] hidden max-w-xs md:block rounded-xl border border-border bg-surface/95 p-3 text-xs shadow-sm backdrop-blur">
                  <p className="flex items-center gap-1.5 font-semibold text-foreground">
                    <MousePointerClick className="size-4 text-primary" aria-hidden /> Start with the worst point
                  </p>
                  <p className="mt-1 text-muted">
                    The pulsing ring marks the worst place for <strong className="text-foreground">{METRIC_SHORT[ev.metric].toLowerCase()}</strong>. Click it,
                    any coloured trail piece, or a row in the list to see fixes.
                  </p>
                  <button
                    type="button"
                    onClick={() => pl.setSelectedId(worstId)}
                    className="pointer-events-auto mt-2 rounded-lg bg-primary px-3 py-1.5 font-semibold text-primary-foreground hover:bg-primary-hover"
                  >
                    Open worst point
                  </button>
                </div>
              )}

              {data && selected && (
                <PointDrawer
                  key={selected.id}
                  point={selected}
                  trail={pl.trailsById.get(selected.trail_id)}
                  result={pl.resultsById.get(selected.id)}
                  metric={ev?.metric ?? pl.metric}
                  rec={pl.recommendation}
                  isWorst={selected.id === worstId}
                  nextWorstId={worstId}
                  busy={pl.evaluating}
                  solarUnit={solarUnit}
                  onAccept={(fixId) => pl.accept(fixId, selected.id)}
                  onClose={close}
                  onGoTo={pl.setSelectedId}
                />
              )}
            </div>
            <KpiStrip kpis={ev?.kpis} burdenPct={ev?.burden.reduction_pct ?? null} metricLabel={METRIC_SHORT[ev?.metric ?? pl.metric]} />
          </main>
        </div>
      )}

      {data && <AssumptionsModal open={assumptionsOpen} onClose={() => setAssumptionsOpen(false)} data={data} />}
    </>
  )
}
