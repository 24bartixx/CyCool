import type { MapPointInfo, MetricId, Trail } from '../api/planner.ts'

export const KIND_LABEL = { segment: 'Trail piece', junction: 'Traffic-light junction', station: 'Bike station' } as const
export const KIND_SHORT = { segment: 'Trail', junction: 'Junction', station: 'Station' } as const

export function pointTitle(p: MapPointInfo): string {
  return p.kind === 'segment' ? p.street : (p.name ?? p.id)
}

export function pointSubtitle(p: MapPointInfo, trail?: Trail): string {
  const where = trail ? `${trail.id} · ${trail.name}` : p.trail_id
  return p.kind === 'segment' ? `${where} · segment ${p.id}` : where
}

export const METRIC_UNIT_HINT: Record<MetricId, string> = {
  water: 'distance to drinking water',
  sun: 'sun exposure',
  heat: 'heat stress (UTCI)',
  combined: 'combined score',
}
