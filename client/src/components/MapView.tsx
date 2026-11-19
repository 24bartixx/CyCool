import L from 'leaflet'
import { Bike, TrafficCone } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Circle, CircleMarker, GeoJSON, MapContainer, Marker, Pane, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import type { Evaluation, MapData, MapPointInfo, MetricId, PointResult } from '../api/planner.ts'
import { dec2, metres } from '../lib/format.ts'
import { FIX_ICON, METRIC_SHORT } from '../lib/icons.tsx'
import { pointTitle } from '../lib/points.ts'
import { cssVar, scoreColor } from '../lib/scale.ts'
import Legend from './Legend.tsx'

type Props = {
  mapData: MapData
  evaluation?: Evaluation
  metric: MetricId
  selectedId?: string
  hoveredId?: string
  onSelect: (id: string) => void
  drawerOpen: boolean
}

const iconCache = new Map<string, L.DivIcon>()
function nodeIcon(kind: 'junction' | 'station', color: string, selected: boolean): L.DivIcon {
  const key = `${kind}|${color}|${selected}`
  const hit = iconCache.get(key)
  if (hit) return hit
  const Glyph = kind === 'junction' ? TrafficCone : Bike
  const html = `<div class="cc-marker cc-marker--${kind}${selected ? ' cc-marker--selected' : ''}" style="width:24px;height:24px;background:${color}">${renderToStaticMarkup(
    <Glyph size={13} strokeWidth={2.5} aria-hidden />,
  )}</div>`
  // stations are drawn up-right of their position so they never hide a junction on the same spot
  const icon = L.divIcon({ html, className: '', iconSize: [24, 24], iconAnchor: kind === 'station' ? [-4, 28] : [12, 12] })
  iconCache.set(key, icon)
  return icon
}

function fixBadge(fixId: string, slot: number): L.DivIcon {
  const Glyph = FIX_ICON[fixId]
  return L.divIcon({
    html: `<div class="cc-fix-badge${fixId === 'INT-03' ? ' cc-fix-badge--water' : ''}">${renderToStaticMarkup(
      <Glyph size={12} strokeWidth={2.5} aria-hidden />,
    )}</div>`,
    className: '',
    iconSize: [22, 22],
    iconAnchor: [11 - slot * 20, 34],
  })
}

const worstRing = L.divIcon({ html: '<div class="cc-worst-ring"></div>', className: '', iconSize: [44, 44], iconAnchor: [22, 22] })

/** Keeps the selected point visible next to the detail drawer. */
function FocusSelected({ point, drawerOpen }: { point?: MapPointInfo; drawerOpen: boolean }) {
  const map = useMap()
  useEffect(() => {
    if (!point) return
    const wide = map.getSize().x > 760
    map.panInside(point.mid_wgs, {
      paddingTopLeft: [60, 60],
      paddingBottomRight: [drawerOpen && wide ? 440 : 60, drawerOpen && !wide ? 360 : 60],
    })
  }, [map, point, drawerOpen])
  return null
}

function pointTooltip(p: MapPointInfo, r: PointResult | undefined, metric: MetricId) {
  return (
    <Tooltip sticky className="cc-tooltip" direction="top" offset={[0, -8]}>
      <strong>{pointTitle(p)}</strong>
      <br />
      {p.trail_id} · {METRIC_SHORT[metric]} score {r ? dec2(r.scores[metric]) : '…'}
    </Tooltip>
  )
}

export default function MapView({ mapData, evaluation, metric, selectedId, hoveredId, onSelect, drawerOpen }: Props) {
  const [showContext, setShowContext] = useState(true)
  const [showFountains, setShowFountains] = useState(true)
  const [showReach, setShowReach] = useState(false)

  const results = useMemo(() => new Map(evaluation?.points.map((p) => [p.id, p])), [evaluation])
  const bounds = useMemo(
    () => L.latLngBounds(mapData.points.flatMap((p) => p.wgs)).pad(0.08),
    [mapData.points],
  )
  const segments = mapData.points.filter((p) => p.kind === 'segment')
  const nodes = mapData.points.filter((p): p is MapPointInfo & { kind: 'junction' | 'station' } => p.kind !== 'segment')
  const pointsById = useMemo(() => new Map(mapData.points.map((p) => [p.id, p])), [mapData.points])
  const worstId = evaluation?.worst[0]
  const worstPoint = worstId ? pointsById.get(worstId) : undefined
  const selected = selectedId ? pointsById.get(selectedId) : undefined
  const hovered = hoveredId ? pointsById.get(hoveredId) : undefined
  const waterOk = Number(mapData.assumptions.find((a) => a.key === 'water_ok_m')?.value ?? 0)

  const fixesByPoint = useMemo(() => {
    const m = new Map<string, string[]>()
    for (const f of evaluation?.plan ?? []) m.set(f.point_id, [...(m.get(f.point_id) ?? []), f.fix_id])
    return m
  }, [evaluation])

  const neutral = cssVar('--color-network')
  const water = cssVar('--color-water')
  const ink = cssVar('--color-foreground')
  const primary = cssVar('--color-primary')

  const highlight = (p: MapPointInfo | undefined, color: string, weight: number) =>
    p?.kind === 'segment' ? (
      <Polyline positions={p.wgs} pathOptions={{ color, weight, opacity: 0.9, lineCap: 'round' }} interactive={false} />
    ) : null

  return (
    <div className="relative h-full w-full">
      <MapContainer bounds={bounds} className="h-full w-full" zoomSnap={0.5} scrollWheelZoom preferCanvas={false} attributionControl>
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · cycle network, solar &amp; fountains: Ajuntament de Viladecans'
          className="cc-basemap"
          maxZoom={19}
        />
        <FocusSelected point={selected} drawerOpen={drawerOpen} />

        <Pane name="context" style={{ zIndex: 380 }}>
          {showContext && (
            <GeoJSON
              data={mapData.context_network}
              interactive={false}
              style={(f) => ({ color: neutral, weight: f?.properties?.cycle ? 2 : 1.25, opacity: 0.9, dashArray: f?.properties?.cycle ? undefined : '3 4' })}
            />
          )}
        </Pane>

        <Pane name="reach" style={{ zIndex: 390 }}>
          {showReach &&
            mapData.fountains.map((f) => (
              <Circle key={f.id} center={f.wgs} radius={waterOk} interactive={false} pathOptions={{ stroke: false, fillColor: water, fillOpacity: 0.1 }} />
            ))}
          {evaluation?.oases.map((o) => (
            <Circle
              key={`oasis-${o.point_id}`}
              center={o.wgs}
              radius={waterOk}
              interactive={false}
              pathOptions={{ color: water, weight: 1.5, dashArray: '4 4', fillColor: water, fillOpacity: 0.08 }}
            />
          ))}
        </Pane>

        <Pane name="trails" style={{ zIndex: 410 }}>
          {highlight(selected, ink, 14)}
          {hovered?.id !== selected?.id && highlight(hovered, primary, 13)}
          {segments.map((p) => {
            const r = results.get(p.id)
            const color = r ? scoreColor(r.scores[metric]) : neutral
            return (
              <Polyline key={p.id} positions={p.wgs} pathOptions={{ color, weight: 7, opacity: 1, lineCap: 'butt' }} interactive={false} />
            )
          })}
          {/* wide invisible hit areas: easier to click than the 7 px line */}
          {segments.map((p) => (
            <Polyline
              key={`hit-${p.id}`}
              positions={p.wgs}
              pathOptions={{ color: '#000', weight: 20, opacity: 0 }}
              eventHandlers={{ click: () => onSelect(p.id) }}
            >
              {pointTooltip(p, results.get(p.id), metric)}
            </Polyline>
          ))}
        </Pane>

        <Pane name="fountains" style={{ zIndex: 420 }}>
          {showFountains &&
            mapData.fountains.map((f) => (
              <CircleMarker key={f.id} center={f.wgs} radius={4} pathOptions={{ color: '#fff', weight: 1.5, fillColor: water, fillOpacity: 1 }}>
                <Tooltip className="cc-tooltip" direction="top" offset={[0, -4]}>
                  Drinking fountain{f.location ? ` · ${f.location}` : ''}
                </Tooltip>
              </CircleMarker>
            ))}
        </Pane>

        {nodes.map((p) => {
          const r = results.get(p.id)
          const color = r ? scoreColor(r.scores[metric]) : neutral
          return (
            <Marker
              key={p.id}
              position={p.mid_wgs}
              icon={nodeIcon(p.kind, color, p.id === selectedId || p.id === hoveredId)}
              eventHandlers={{ click: () => onSelect(p.id) }}
              keyboard
              title={pointTitle(p)}
              zIndexOffset={p.kind === 'station' ? 100 : 0}
            >
              <Tooltip className="cc-tooltip" direction="top" offset={[0, -14]}>
                <strong>{pointTitle(p)}</strong>
                <br />
                {p.trail_id} · {METRIC_SHORT[metric]} score {r ? dec2(r.scores[metric]) : '…'}
                <br />
                <span style={{ color: 'var(--color-warning)' }}>Approximate location (synthetic, moved {metres(p.snap_distance_m)})</span>
              </Tooltip>
            </Marker>
          )
        })}

        {[...fixesByPoint.entries()].flatMap(([pid, fixes]) => {
          const p = pointsById.get(pid)
          return p
            ? fixes.map((fid, slot) => (
                <Marker key={`fix-${pid}-${fid}`} position={p.mid_wgs} icon={fixBadge(fid, slot)} interactive={false} zIndexOffset={500} />
              ))
            : []
        })}

        {worstPoint && <Marker position={worstPoint.mid_wgs} icon={worstRing} interactive={false} zIndexOffset={-100} />}
      </MapContainer>

      {/* layer toggles */}
      <fieldset className="absolute right-3 top-3 z-[1000] hidden rounded-xl border border-border bg-surface/95 px-3 py-2 text-xs shadow-sm backdrop-blur md:block">
        <legend className="sr-only">Map layers</legend>
        {[
          { label: 'Drinking fountains', checked: showFountains, set: setShowFountains },
          { label: `${waterOk} m water reach`, checked: showReach, set: setShowReach },
          { label: 'Rest of the network', checked: showContext, set: setShowContext },
        ].map((o) => (
          <label key={o.label} className="flex cursor-pointer items-center gap-2 py-0.5">
            <input type="checkbox" checked={o.checked} onChange={(e) => o.set(e.target.checked)} className="accent-primary" />
            {o.label}
          </label>
        ))}
      </fieldset>

      <Legend metric={metric} />
    </div>
  )
}
