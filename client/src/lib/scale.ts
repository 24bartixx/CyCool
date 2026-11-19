// Score (0 = fine ... 1 = worst) -> colour class. Colours are read from theme/colors.css.
//
// The class bounds are not fixed score values: per metric they are percentiles of today's network (the scores with
// no fixes, see computeBreaks). So the map shows where a point ranks, and a fix still turns it greener because the
// bounds stay those of today. Display only: scores are unchanged.

import { createContext, useContext } from 'react'
import type { MetricId } from '../api/planner.ts'

export const SCORE_CLASSES = [
  { key: 'fine', token: '--color-score-fine', label: 'Fine' },
  { key: '1', token: '--color-score-1', label: 'Low' },
  { key: '2', token: '--color-score-2', label: 'Moderate' },
  { key: '3', token: '--color-score-3', label: 'High' },
  { key: '4', token: '--color-score-4', label: 'Very high' },
  { key: '5', token: '--color-score-5', label: 'Worst' },
] as const

export const FINE_BELOW = 0.05

/** Percentiles of today's not-fine scores that split Low | Moderate | High | Very high | Worst. */
const CLASS_PERCENTILES = [40, 65, 85, 95]

/** The 4 upper bounds of the classes Low ... Very high; a score at or above the last one is Worst. */
export type Breaks = readonly number[]
export type ScoreBreaks = Partial<Record<MetricId, Breaks>>

/** Fallback before the map data arrives. */
const EVEN_BREAKS: Breaks = [0.2, 0.4, 0.6, 0.8]

function percentile(sorted: number[], p: number): number {
  const at = ((sorted.length - 1) * p) / 100
  const lo = Math.floor(at)
  const hi = Math.min(lo + 1, sorted.length - 1)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (at - lo)
}

/**
 * Class bounds from today's scores of one metric. When bounds tie (e.g. many water scores clamped at 1), the class
 * in between stays empty and the tied points land in the higher one.
 */
export function computeBreaks(scores: number[]): Breaks {
  const sorted = scores.filter((s) => s >= FINE_BELOW).sort((a, b) => a - b)
  if (!sorted.length) return EVEN_BREAKS
  return CLASS_PERCENTILES.map((p) => percentile(sorted, p))
}

export function scoreClassIndex(score: number, breaks: Breaks): number {
  if (score < FINE_BELOW) return 0
  const i = breaks.findIndex((u) => score < u)
  return i === -1 ? breaks.length + 1 : i + 1
}

/** [lower, upper) score range of a class; equal ends mean the class is empty (tied bounds). */
export function classRange(index: number, breaks: Breaks): [number, number] {
  if (index === 0) return [0, FINE_BELOW]
  return [index === 1 ? FINE_BELOW : breaks[index - 2], index > breaks.length ? 1 : breaks[index - 1]]
}

const cache = new Map<string, string>()
export function cssVar(token: string): string {
  const hit = cache.get(token)
  if (hit) return hit
  const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim() || '#888888'
  cache.set(token, value)
  return value
}

// Vite hot-swaps theme/colors.css without a reload: forget the cached values so the next render reads the new ones.
if (import.meta.hot) import.meta.hot.on('vite:afterUpdate', () => cache.clear())

export const scoreColor = (score: number, breaks: Breaks) => cssVar(SCORE_CLASSES[scoreClassIndex(score, breaks)].token)

/** Today's class bounds per metric, provided once by the planner page. */
export const ScoreBreaksContext = createContext<ScoreBreaks>({})

/** Class bounds of a metric, with its colour and class lookups. */
export function useScoreScale(metric: MetricId) {
  const breaks = useContext(ScoreBreaksContext)[metric] ?? EVEN_BREAKS
  return {
    breaks,
    color: (score: number) => scoreColor(score, breaks),
    cls: (score: number) => SCORE_CLASSES[scoreClassIndex(score, breaks)],
  }
}
