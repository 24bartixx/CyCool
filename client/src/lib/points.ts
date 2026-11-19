import type { MapPointInfo, MetricId, PointKind, PointResult, Trail } from '../api/planner.ts'

export const POINT_KINDS: readonly PointKind[] = ['segment', 'junction', 'station']

/**
 * Ids of the points still to fix (priority > 0) of the given kinds, worst first. The same rule as the backend's
 * `worst` (highest priority, ties by id), narrowed by the "Where to look" filter. Its first id is the worst point
 * everywhere in the UI: the list's #1, the ring on the map, "Go to worst point" and the details' "Worst" badge.
 */
export function rankWorst(
  points: readonly PointResult[],
  pointsById: ReadonlyMap<string, MapPointInfo>,
  kinds: ReadonlySet<PointKind>,
): string[] {
  return points
    .filter((r) => {
      const kind = pointsById.get(r.id)?.kind
      return r.priority > 0 && kind !== undefined && kinds.has(kind)
    })
    .sort((a, b) => b.priority - a.priority || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
    .map((r) => r.id)
}

export const KIND_LABEL = { segment: 'Trail piece', junction: 'Traffic-light junction', station: 'Bike station' } as const
export const KIND_SHORT = { segment: 'Trail', junction: 'Junction', station: 'Station' } as const

export function pointTitle(p: MapPointInfo): string {
  return p.kind === 'segment' ? p.street : (p.name ?? p.id)
}

export function pointSubtitle(p: MapPointInfo, trail?: Trail): string {
  const parts = [trail?.name, p.kind === 'segment' ? `segment ${p.id}` : undefined]
  return parts.filter(Boolean).join(' · ')
}

export const METRIC_UNIT_HINT: Record<MetricId, string> = {
  water: 'distance to drinking water',
  sun: 'sun exposure',
  heat: 'heat stress (UTCI)',
  combined: 'combined score',
}
