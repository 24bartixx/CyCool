import { dec2 } from '../lib/format.ts'
import { SCORE_CLASSES, scoreClassIndex, scoreColor } from '../lib/scale.ts'

/** Score shown as a colour swatch plus the number and class name, so colour is never the only cue. */
export default function ScoreChip({ score, showLabel = false }: { score: number; showLabel?: boolean }) {
  const cls = SCORE_CLASSES[scoreClassIndex(score)]
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold tabular-nums text-foreground" title={`Score ${dec2(score)} (${cls.label})`}>
      <span className="size-2.5 shrink-0 rounded-full ring-1 ring-black/10" style={{ background: scoreColor(score) }} aria-hidden />
      {dec2(score)}
      {showLabel && <span className="font-normal text-muted">{cls.label}</span>}
    </span>
  )
}
