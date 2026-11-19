import type { MetricId } from '../api/planner.ts'
import { dec2 } from '../lib/format.ts'
import { useScoreScale } from '../lib/scale.ts'

/** Score shown as a colour swatch plus the number and class name, so colour is never the only cue. */
export default function ScoreChip({ score, metric, showLabel = false }: { score: number; metric: MetricId; showLabel?: boolean }) {
  const scale = useScoreScale(metric)
  const cls = scale.cls(score)
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold tabular-nums text-foreground" title={`Score ${dec2(score)} (${cls.label})`}>
      <span className="size-2.5 shrink-0 rounded-full ring-1 ring-black/10" style={{ background: scale.color(score) }} aria-hidden />
      {dec2(score)}
      {showLabel && <span className="font-normal text-muted">{cls.label}</span>}
    </span>
  )
}
