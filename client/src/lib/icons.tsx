import {
  Bike,
  Droplets,
  Flame,
  Gauge,
  Leaf,
  PaintRoller,
  SunMedium,
  ThermometerSnowflake,
  Timer,
  TreeDeciduous,
  Umbrella,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { MetricId } from '../api/planner.ts'

export const METRIC_ICON: Record<MetricId, LucideIcon> = {
  water: Droplets,
  sun: SunMedium,
  heat: Flame,
  combined: Gauge,
}

export const FIX_ICON: Record<string, LucideIcon> = {
  'INT-01': TreeDeciduous,
  'INT-02': Umbrella,
  'INT-03': Droplets,
  'INT-04': PaintRoller,
  'INT-05': Timer,
  'INT-06': Zap,
}

/** KPI strip tiles (the headline burden tile uses METRIC_ICON of the selected metric). */
export const KPI_ICON = {
  comfort: Bike,
  water: Droplets,
  cooling: ThermometerSnowflake,
  co2: Leaf,
} satisfies Record<string, LucideIcon>

export const METRIC_SHORT: Record<MetricId, string> = {
  water: 'Water',
  sun: 'Sun',
  heat: 'Heat',
  combined: 'Combined',
}
