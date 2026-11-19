import { apiGet, apiPost } from './client.ts'

export type MetricId = 'water' | 'sun' | 'heat' | 'combined'
export type PointKind = 'segment' | 'junction' | 'station'
export type LatLng = [number, number]

export type Trail = {
  id: string
  name: string
  streets: string[]
  cycleway_type: string
  real_length_m: number
  synthetic_length_m: number
  utci_2pm_c: number
  surface_temp_c: number
  shade_2pm_pct: number
  nearest_shelter_id: string
  nearest_shelter_name: string | null
  risk_level: string
}

export type MapPointInfo = {
  id: string
  kind: PointKind
  trail_id: string
  street: string
  length_m: number
  solar: number
  wgs: LatLng[]
  mid_wgs: LatLng
  fountain_dist_m: number
  cycle_class?: string
  name?: string
  notes?: string
  /** Junctions only: how far the synthetic location was moved onto its trail. */
  snap_distance_m?: number
  /** Stations only: the real AMBici station's address, docks and distance to its (nearest) trail. */
  address?: string | null
  bike_racks?: number | null
  trail_dist_m?: number
  /** Stations matched to a VAS-R1 station (EST-B01/B02), whose synthetic heat data they carry. */
  vas_id?: string
  wait_s?: number
  shade_pct?: number
  temp_anomaly_c?: number
}

export type CatalogueItem = {
  id: string
  label: string
  category: string
  description: string
  unit: string
  capex_eur: number
  opex_eur_yr: number
  utci_reduction_c: number
  surface_temp_reduction_c: number
  co2_kg_yr: number
  deployment_weeks: number
  notes: string
  allowed_on: PointKind[]
  priced_per_m: boolean
  effects: string[]
}

export type Assumption = {
  key: string
  label: string
  value: number | string | string[]
  unit: string
  source: string
  note: string
}

export type MetricInfo = { id: MetricId; label: string; description: string }

export type MapData = {
  trails: Trail[]
  points: MapPointInfo[]
  fountains: { id: string; location: string | null; wgs: LatLng }[]
  context_network: GeoJSON.FeatureCollection
  catalogue: CatalogueItem[]
  assumptions: Assumption[]
  solar_range: [number, number]
  metrics: MetricInfo[]
}

export type Scores = Record<MetricId, number>

export type PointResult = {
  id: string
  scores: Scores
  raw: {
    utci_c: number
    solar: number
    water_dist_m: number
    wait_s?: number
    shade_pct?: number
    wait_exposure?: number
  }
  priority: number
}

export type NetworkKpis = {
  trail_km: number
  comfortable_km: number
  /** Trail length with UTCI below the "very strong heat stress" threshold (strong_heat_utci_c). */
  below_strong_heat_km: number
  water_reachable_km: number
}

export type Kpis = {
  before: NetworkKpis
  after: NetworkKpis
  comfortable_km_gain: number
  utci_drop_avg_c: number | null
  utci_drop_max_c: number | null
  points_cooled: number
  utci_drop_trail_avg_c: number | null
  utci_cooled_trail_km: number
  co2_t_per_year: number
  capex_eur: number
  opex_eur_per_year: number
  eur_per_comfortable_km: number | null
}

export type AcceptedFix = { fix_id: string; point_id: string }

export type Evaluation = {
  metric: MetricId
  points: PointResult[]
  worst: string[]
  budget: { total: number; spent: number; remaining: number }
  plan: (AcceptedFix & { label: string; cost_eur: number; opex_eur_yr: number })[]
  oases: { point_id: string; wgs: LatLng }[]
  burden: { baseline: number; current: number; reduction_pct: number | null }
  kpis: Kpis
}

export type OptionStatus = 'available' | 'over_budget' | 'no_effect' | 'applied'

export type FixImpact = {
  metric: MetricId
  before: number
  after: number
  measurement?: { before: number; after: number; unit: string }
}

export type FixOption = {
  fix_id: string
  label: string
  status: OptionStatus
  cost_eur: number
  effects: string[]
  description?: string
  opex_eur_yr?: number
  deployment_weeks?: number
  local_before?: number
  local_after?: number
  local_impacts?: FixImpact[]
  network_reduction_pct?: number
  value_pct_per_10k?: number | null
}

export type Recommendation = {
  point_id: string
  metric: MetricId
  remaining_eur: number
  local_score: number
  options: FixOption[]
}

export type PlanRequest = { metric: MetricId; budget: number; accepted: AcceptedFix[] }

export const getMapData = (signal?: AbortSignal) => apiGet<MapData>('/map-data', signal)
export const postEvaluate = (req: PlanRequest, signal?: AbortSignal) => apiPost<Evaluation>('/evaluate', req, signal)
export const postRecommend = (req: PlanRequest & { point_id: string }, signal?: AbortSignal) =>
  apiPost<Recommendation>('/recommend', req, signal)
