import {
  Bike,
  Droplet,
  Droplets,
  Euro,
  Flame,
  Gauge,
  Leaf,
  PaintRoller,
  SunMedium,
  ThermometerSnowflake,
  ThermometerSun,
  Timer,
  TreeDeciduous,
  Umbrella,
  Users,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { MetricId } from '../api/planner.ts'
import { OasisIcon } from './OasisIcon.tsx'

export const METRIC_ICON: Record<MetricId, LucideIcon> = {
  water: Droplets,
  sun: SunMedium,
  heat: Flame,
  combined: Gauge,
}

export const FIX_ICON: Record<string, LucideIcon> = {
  'INT-01': TreeDeciduous,
  'INT-02': Umbrella,
  'INT-03': OasisIcon,
  'INT-04': PaintRoller,
  'INT-05': Timer,
  'INT-06': Zap,
  'INT-09': Droplet,
}

/** Colour of each fix's icon chip and map badge: the oasis aquamarine, the fountain water blue, others the brand. */
export const FIX_TONE: Record<string, 'oasis' | 'water'> = { 'INT-03': 'oasis', 'INT-09': 'water' }
const FIX_BG = { oasis: 'bg-oasis', water: 'bg-water' } as const

export function fixBg(fixId: string): string {
  const tone = FIX_TONE[fixId]
  return tone ? FIX_BG[tone] : 'bg-primary'
}

/** KPI strip tiles (the headline burden tile uses METRIC_ICON of the selected metric). */
export const KPI_ICON = {
  comfort: Bike,
  heatStress: ThermometerSun,
  water: Droplets,
  cooling: ThermometerSnowflake,
  co2: Leaf,
  riders: Users,
  cost: Euro,
} satisfies Record<string, LucideIcon>

export const METRIC_SHORT: Record<MetricId, string> = {
  water: 'Water',
  sun: 'Sun',
  heat: 'Heat',
  combined: 'Combined',
}
