// Score (0 = fine ... 1 = worst) -> colour class. Colours are read from theme/colors.css.

export const SCORE_CLASSES = [
  { key: 'fine', token: '--color-score-fine', label: 'Fine', range: '< 0.05' },
  { key: '1', token: '--color-score-1', label: 'Low', range: '0.05–0.2' },
  { key: '2', token: '--color-score-2', label: 'Moderate', range: '0.2–0.4' },
  { key: '3', token: '--color-score-3', label: 'High', range: '0.4–0.6' },
  { key: '4', token: '--color-score-4', label: 'Very high', range: '0.6–0.8' },
  { key: '5', token: '--color-score-5', label: 'Worst', range: '0.8–1' },
] as const

export const FINE_BELOW = 0.05
const UPPER = [0.2, 0.4, 0.6, 0.8]

export function scoreClassIndex(score: number): number {
  if (score < FINE_BELOW) return 0
  const i = UPPER.findIndex((u) => score < u)
  return i === -1 ? 5 : i + 1
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

export const scoreColor =(score: number) => cssVar(SCORE_CLASSES[scoreClassIndex(score)].token)
