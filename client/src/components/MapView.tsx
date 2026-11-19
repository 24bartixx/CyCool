import L from "leaflet";
import { Bike, Droplet, House, Target, TrafficCone } from "lucide-react";
import {
  memo,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import { renderToStaticMarkup } from "react-dom/server";
import {
  AttributionControl,
  Circle,
  GeoJSON,
  MapContainer,
  Marker,
  Pane,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvent,
} from "react-leaflet";
import type {
  Evaluation,
  LatLng,
  MapData,
  MapPointInfo,
  MetricId,
  PointKind,
  PointResult,
} from "../api/planner.ts";
import { dec2, metres } from "../lib/format.ts";
import { FIX_ICON, METRIC_SHORT } from "../lib/icons.tsx";
import { isOffTrail, pointTitle } from "../lib/points.ts";
import { cssVar, scoreColor as colorFor, useScoreScale } from "../lib/scale.ts";
import Legend from "./Legend.tsx";

type Props = {
  mapData: MapData;
  evaluation?: Evaluation;
  metric: MetricId;
  /**
   * Point kinds picked in "Where to look". The others are drawn grey (not hidden: the trail lines locate the
   * markers on them, and points in the plan must stay reachable) and stay clickable.
   */
  kinds: ReadonlySet<PointKind>;
  /** The worst point among those kinds (see rankWorst); ringed, and the target of "Go to worst point". */
  worstId?: string;
  selectedId?: string;
  hoveredId?: string;
  onSelect: (id: string) => void;
  /** Changes on every pick (list, map or button), even of the same point, so the map flies to it each time. */
  focusRequest: number;
  /** The details drawer covers part of the map (smaller screens), so the selected point must stay clear of it. */
  drawerOverMap: boolean;
  /** The selected point's details, shown in a popup above the point (wide screens). */
  popup?: ReactNode;
  /** Clicking the map outside the popup closes it. */
  onClosePopup: () => void;
};

const iconCache = new Map<string, L.DivIcon>();
/** A kind left out of "Where to look": a smaller grey marker, so the eye goes to the kinds in play. */
const MUTED_MARKER_PX = 18;

function nodeIcon(
  kind: "junction" | "station",
  color: string,
  highlight: "selected" | "hovered" | undefined,
  muted = false,
): L.DivIcon {
  const key = `${kind}|${color}|${highlight}|${muted}`;
  const hit = iconCache.get(key);
  if (hit) return hit;
  const Glyph = kind === "junction" ? TrafficCone : Bike;
  const px = muted ? MUTED_MARKER_PX : 24;
  const html = `<div class="cc-marker cc-marker--${kind}${highlight ? ` cc-marker--${highlight}` : ""}${muted ? " cc-marker--muted" : ""}" style="width:${px}px;height:${px}px;background:${color}">${renderToStaticMarkup(
    <Glyph size={muted ? 10 : 13} strokeWidth={2.5} aria-hidden />,
  )}</div>`;
  // stations are drawn up-right of their position (4 px off it) so they never hide a junction on the same spot
  const icon = L.divIcon({
    html,
    className: "",
    iconSize: [px, px],
    iconAnchor: kind === "station" ? [-4, px + 4] : [px / 2, px / 2],
  });
  iconCache.set(key, icon);
  return icon;
}

/**
 * A drinking fountain: context, not a point to fix, so smaller than the junction and station markers and always
 * water blue. A single droplet, where the Cyclist Oasis fix badge shows several (INT-03 in FIX_ICON).
 */
const FOUNTAIN_PX = 18;
/** Tint of the water reach area around fountains and oases (applied once to the whole pane, see the reach pane). */
const REACH_OPACITY = 0.1;
const fountainIcon = L.divIcon({
  html: `<div class="cc-marker cc-marker--fountain" style="width:${FOUNTAIN_PX}px;height:${FOUNTAIN_PX}px">${renderToStaticMarkup(
    <Droplet size={10} strokeWidth={2.75} aria-hidden />,
  )}</div>`,
  // not clickable (only a tooltip), so no pointer cursor; see .cc-fountain-icon
  className: "cc-fountain-icon",
  iconSize: [FOUNTAIN_PX, FOUNTAIN_PX],
  iconAnchor: [FOUNTAIN_PX / 2, FOUNTAIN_PX / 2],
});

/** A Bicibox secure bike parking: context like a fountain, a small charcoal "P" square (AMBici stations are larger and
    score-coloured). */
const BIKE_PARKING_PX = 15;
const bikeParkingIcon = L.divIcon({
  html: `<div class="cc-marker cc-marker--bike-parking" style="width:${BIKE_PARKING_PX}px;height:${BIKE_PARKING_PX}px">P</div>`,
  className: "cc-fountain-icon",
  iconSize: [BIKE_PARKING_PX, BIKE_PARKING_PX],
  iconAnchor: [BIKE_PARKING_PX / 2, BIKE_PARKING_PX / 2],
});

/** Tint of the shade reach area around parks and oases (applied once to the whole pane, like the water reach). */
const SHADE_REACH_OPACITY = 0.3;
/**
 * Reach drawn around a park: a park is a large shaded area worth a longer detour than an oasis pergola (which keeps
 * the water_ok_m "short detour"). Display only, it never changes a score or KPI, so it is not in assumptions.yaml.
 */
const PARK_SHADE_REACH_M = 150;

/** Metres per screen pixel at a zoom level and latitude (Web Mercator, 256 px tiles). */
function metresPerPixel(zoom: number, lat: number): number {
  return (40075016.686 * Math.cos((lat * Math.PI) / 180)) / 2 ** (zoom + 8);
}

/**
 * Area within `radius` metres of a park: each park drawn filled, with a round-joined stroke 2 × radius wide, which
 * together cover exactly the park grown by the radius (a buffer). Leaflet strokes are in pixels, so the width is
 * recomputed on every zoom. Display only: parks never change a score.
 */
function ParkReach({
  parks,
  radius,
  color,
}: {
  parks: MapData["parks"];
  radius: number;
  color: string;
}) {
  const map = useMap();
  const [zoom, setZoom] = useState(() => map.getZoom());
  useMapEvent("zoomend", () => setZoom(map.getZoom()));
  // noClip: Leaflet clips paths just outside the view, and the wide stroke would then also run along the clip edge.
  const style = useMemo<L.PolylineOptions>(
    () => ({
      noClip: true,
      color,
      weight: (2 * radius) / metresPerPixel(zoom, map.getCenter().lat),
      opacity: 1,
      lineJoin: "round",
      lineCap: "round",
      fillColor: color,
      fillOpacity: 1,
    }),
    [color, radius, zoom, map],
  );
  return <GeoJSON data={parks} style={style} interactive={false} />;
}

type ParkProps = MapData["parks"]["features"][number]["properties"];

/** Park tooltip as a DOM node, so an OSM name is shown as text, never parsed as HTML. */
function parkTooltip(props: ParkProps): HTMLElement {
  const el = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = `Park · ${props.name ?? "unnamed"}`;
  el.append(
    title,
    document.createElement("br"),
    `${Math.round(props.area_m2).toLocaleString("en")} m² · OpenStreetMap`,
  );
  return el;
}

const badgeCache = new Map<string, L.DivIcon>();

/** Cached like nodeIcon: a new icon object on every render would make each badge swap its DOM element. */
function fixBadge(fixId: string, slot: number): L.DivIcon {
  const key = `${fixId}|${slot}`;
  const hit = badgeCache.get(key);
  if (hit) return hit;
  const Glyph = FIX_ICON[fixId];
  const icon = L.divIcon({
    html: `<div class="cc-fix-badge${fixId === "INT-03" ? " cc-fix-badge--water" : ""}">${renderToStaticMarkup(
      <Glyph size={12} strokeWidth={2.5} aria-hidden />,
    )}</div>`,
    className: "",
    iconSize: [22, 22],
    iconAnchor: [11 - slot * 20, 34],
  });
  badgeCache.set(key, icon);
  return icon;
}

const worstRing = L.divIcon({
  html: '<div class="cc-worst-ring"></div>',
  className: "",
  iconSize: [44, 44],
  iconAnchor: [22, 22],
});

/**
 * Leaflet only re-measures its container when the window resizes, but the page layout can also resize the map
 * (columns appearing at a breakpoint). Re-measure, and pan by however far the left edge moved so the map stays
 * still on screen instead of jumping sideways.
 */
function syncSize(map: L.Map, lastLeft: RefObject<number | undefined>) {
  const left = map.getContainer().getBoundingClientRect().left;
  const shift = lastLeft.current === undefined ? 0 : left - lastLeft.current;
  lastLeft.current = left;
  map.invalidateSize({ pan: !shift });
  if (shift) map.panBy([shift, 0], { animate: false });
}

/**
 * Width of the lanes' score lines at street level (FOCUS_ZOOM and closer). Zoomed out they get 1 px thinner per
 * zoom level, down to LANE_MIN_PX, so lanes next to each other don't run into one another.
 */
const LANE_PX = 6;
const LANE_MIN_PX = 3;
/** A lane left out of "Where to look" is grey and this share of a score line's width (at least MUTED_LANE_MIN_PX). */
const MUTED_LANE_SHARE = 0.6;
const MUTED_LANE_MIN_PX = 1.5;
/** Width of the solid selection-coloured line drawn over the selected segment, at street level (see SegmentHighlight). */
const SELECTED_LINE_PX = 19;
const HOVERED_LINE_PX = 13;

/** Zoom the map flies to for a selected point (street level), unless the planner is already zoomed in closer. */
const FOCUS_ZOOM = 17;
/** Tailwind's `md`: from here the details drawer is a 400 px right-hand panel, below it a bottom sheet up to 70% high. */
const DRAWER_SIDE_PANEL = "(min-width: 48rem)";
const DRAWER_PANEL_PX = 400;
const DRAWER_SHEET_SHARE = 0.7;

// ---- the details popup (wide screens) ----

const POPUP_WIDTH = 360;
/** Gap kept between the popup and the map's edges or the controls drawn over the map. */
const POPUP_MARGIN = 12;
/** Map height the popup leaves free for its tip and the point under it; the details scroll inside if they need more. */
const POPUP_RESERVED = 100;
const POPUP_MIN_HEIGHT = 220;
/** Space left between the popup's tip and the top of the selected line or marker. */
const POPUP_GAP = 36;
/**
 * Where the popup's tip sits, in pixels from its anchor (see popupAnchor). Leaflet's [0, 7] puts the tip right on
 * the anchor; these lift it POPUP_GAP clear of the selected line (SELECTED_LINE_PX wide, round caps) or marker
 * (24 px plus its 4 px outline; stations are drawn up-right of their spot, see nodeIcon).
 */
const POPUP_OFFSET: Record<MapPointInfo["kind"], [number, number]> = {
  segment: [0, -4 - POPUP_GAP],
  junction: [0, -11 - POPUP_GAP],
  station: [16, -27 - POPUP_GAP],
};

/**
 * Where the popup hangs from. A segment's popup sits above its whole line (at the line's northernmost point,
 * over its middle), so a sloping segment never runs up under the popup; markers hang it from their spot.
 */
function popupAnchor(point: MapPointInfo): LatLng {
  if (point.kind !== "segment") return point.mid_wgs;
  return [Math.max(...point.wgs.map(([lat]) => lat)), point.mid_wgs[1]];
}

type Box = { left: number; top: number; right: number; bottom: number };

const clamp = (v: number, lo: number, hi: number) =>
  Math.max(lo, Math.min(v, hi));
const overlap = (a: Box, b: Box) =>
  Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) *
  Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));

/** The map overlays and Leaflet controls, in map pixels. They cover the popup. */
function mapObstacles(map: L.Map): Box[] {
  const base = map.getContainer().getBoundingClientRect();
  const els =
    map
      .getContainer()
      .parentElement?.querySelectorAll(
        "[data-map-overlay], .leaflet-control",
      ) ?? [];
  return Array.from(els, (el) => el.getBoundingClientRect())
    .filter((r) => r.width > 0 && r.height > 0)
    .map((r) => ({
      left: r.left - base.left,
      top: r.top - base.top,
      right: r.right - base.left,
      bottom: r.bottom - base.top,
    }));
}

/**
 * Where on the map the point should land: popup above, point below, the pair centred in the map, unless that
 * puts them under the legend or the controls; then the nearest spot beside or below those.
 */
function placePoint(
  size: L.Point,
  pop: { width: number; above: number; dx: number },
  own: Box,
  obstacles: Box[],
): L.Point {
  const m = POPUP_MARGIN;
  const half = pop.width / 2;
  const [xLo, xHi] = [m + half - pop.dx, size.x - m - half - pop.dx];
  const [yLo, yHi] = [m + pop.above, size.y - m - own.bottom];
  const x0 = clamp(size.x / 2 - pop.dx, xLo, xHi);
  const y0 = clamp((size.y + pop.above - own.bottom) / 2, yLo, yHi);
  const xs = [
    x0,
    ...obstacles.flatMap((o) => [
      o.right + m + half - pop.dx,
      o.left - m - half - pop.dx,
    ]),
  ];
  const ys = [
    y0,
    ...obstacles.flatMap((o) => [
      o.bottom + m + pop.above,
      o.top - m - own.bottom,
    ]),
  ];

  let best = { cost: Infinity, at: L.point(x0, y0) };
  for (const xc of xs) {
    for (const yc of ys) {
      const [x, y] = [clamp(xc, xLo, xHi), clamp(yc, yLo, yHi)];
      const boxes: Box[] = [
        {
          left: x + pop.dx - half,
          right: x + pop.dx + half,
          top: y - pop.above,
          bottom: y,
        },
        {
          left: x + own.left,
          right: x + own.right,
          top: y + own.top,
          bottom: y + own.bottom,
        },
      ];
      const covered = boxes.reduce(
        (sum, b) => sum + obstacles.reduce((s, o) => s + overlap(b, o), 0),
        0,
      );
      // Being covered weighs far more than being moved off centre.
      const cost = covered * 100 + Math.hypot(x - x0, y - y0);
      if (cost < best.cost) best = { cost, at: L.point(x, y) };
    }
  }
  return best.at;
}

/** The view that shows the open popup and its point together (see placePoint). */
function viewWithPopup(
  map: L.Map,
  point: MapPointInfo,
  popup: L.Popup,
  maxZoom: number,
) {
  const size = map.getSize();
  const coords = point.kind === "segment" ? point.wgs : [point.mid_wgs];
  const zoom = Math.min(
    map.getBoundsZoom(L.latLngBounds(coords), false, L.point(96, 96)),
    maxZoom,
  );
  const anchor = map.project(popupAnchor(point), zoom);
  // The point's own extent around its anchor at that zoom, plus room for the marker or the line's width.
  const rel = coords.map((c) => map.project(c, zoom).subtract(anchor));
  const reach = 16;
  const own: Box = {
    left: Math.min(...rel.map((r) => r.x)) - reach,
    right: Math.max(...rel.map((r) => r.x)) + reach,
    top: Math.min(...rel.map((r) => r.y)) - reach,
    bottom: Math.max(...rel.map((r) => r.y)) + reach,
  };
  // Leaflet hangs the popup's bottom margin edge `offset` pixels from the point (DivOverlay._updatePosition).
  const el = popup.getElement()!;
  const [dx, dy] = POPUP_OFFSET[point.kind];
  const above =
    el.offsetHeight + (parseFloat(getComputedStyle(el).marginBottom) || 0) - dy;
  const at = placePoint(
    size,
    { width: el.offsetWidth, above, dx },
    own,
    mapObstacles(map),
  );
  return {
    zoom,
    center: map.unproject(anchor.add(size.divideBy(2)).subtract(at), zoom),
  };
}

/**
 * Leaflet's popup, filled by React through a portal, open above the selected point. It is mounted once per
 * point (keyed by id). A click on the map itself closes it, like any map popup.
 */
function PointPopup({
  point,
  popupRef,
  onClose,
  children,
}: {
  point: MapPointInfo;
  popupRef: RefObject<L.Popup | null>;
  onClose: () => void;
  children: ReactNode;
}) {
  const map = useMap();
  const [content] = useState(() => document.createElement("div"));
  const [popup] = useState(() =>
    L.popup({
      className: "cc-popup",
      offset: POPUP_OFFSET[point.kind],
      minWidth: POPUP_WIDTH,
      maxWidth: POPUP_WIDTH,
      // React owns opening and closing, and FollowLayout does the panning.
      autoPan: false,
      closeButton: false,
      autoClose: false,
      closeOnClick: false,
      closeOnEscapeKey: false,
    }).setContent(content),
  );
  useMapEvent("click", onClose);

  // A layout effect, so the popup is on the map before any passive effect runs: the details focus their close
  // button, and FollowLayout measures the popup to place it.
  useLayoutEffect(() => {
    const fitHeight = () =>
      content.style.setProperty(
        "--cc-popup-max-h",
        `${Math.max(POPUP_MIN_HEIGHT, map.getSize().y - POPUP_RESERVED)}px`,
      );
    fitHeight();
    popup.setLatLng(popupAnchor(point)).openOn(map);
    popupRef.current = popup;
    map.on("resize", fitHeight);
    return () => {
      map.off("resize", fitHeight);
      popup.remove();
      if (popupRef.current === popup) popupRef.current = null;
    };
  }, [map, popup, content, point, popupRef]);

  return createPortal(children, content);
}

/** Keeps Leaflet in step with its container, and flies to the selected point each time one is picked. */
function FollowLayout({
  point,
  drawerOverMap,
  focusRequest,
  popupRef,
}: {
  point?: MapPointInfo;
  drawerOverMap: boolean;
  focusRequest: number;
  popupRef: RefObject<L.Popup | null>;
}) {
  const map = useMap();
  const lastLeft = useRef<number>(undefined);

  useEffect(() => {
    const observer = new ResizeObserver(() => syncSize(map, lastLeft));
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);

  useEffect(() => {
    if (!point) return;
    // The layout may have changed in this same render: measure the map before moving it.
    syncSize(map, lastLeft);
    const maxZoom = Math.max(FOCUS_ZOOM, map.getZoom());
    const animate = !window.matchMedia("(prefers-reduced-motion: reduce)")
      .matches;

    // Wide screens: the details popup is already open above the point (PointPopup opens it in a layout effect).
    const popup = popupRef.current;
    if (popup?.isOpen()) {
      const { center, zoom } = viewWithPopup(map, point, popup, maxZoom);
      if (animate) map.flyTo(center, zoom, { duration: 0.8 });
      else map.setView(center, zoom, { animate: false });
      return;
    }

    const size = map.getSize();
    const pad = 40;
    // Centre the point in the part of the map the details drawer leaves uncovered.
    const sidePanel = window.matchMedia(DRAWER_SIDE_PANEL).matches;
    const right = drawerOverMap && sidePanel ? DRAWER_PANEL_PX : 0;
    const bottom =
      drawerOverMap && !sidePanel
        ? Math.min(Math.round(size.y * DRAWER_SHEET_SHARE), size.y - 3 * pad)
        : 0;
    const target = L.latLngBounds(
      point.kind === "segment" ? point.wgs : [point.mid_wgs],
    );
    const options: L.FitBoundsOptions = {
      paddingTopLeft: L.point(pad, pad),
      paddingBottomRight: L.point(right + pad, Math.max(0, bottom) + pad),
      maxZoom,
    };
    if (animate) map.flyToBounds(target, { ...options, duration: 0.8 });
    else map.fitBounds(target, { ...options, animate: false });
    // focusRequest: picking the same point again still brings the map back to it.
  }, [map, point, drawerOverMap, focusRequest, popupRef]);
  return null;
}

/** Extra width of the soft glow around the selected line, beyond its casing. */
const GLOW_PX = 10;
/** Below this core width the flowing dashes would crowd the core; they are left out. */
const FLOW_MIN_CORE_PX = 6;

/**
 * A line over a segment, `weight` wide at street level (FOCUS_ZOOM), narrowing by 4 px per zoom level out down to
 * just wider than the lane: zoomed out, a 50 m segment is only a few pixels long, and a full-width line would
 * swamp it.
 *
 * Without `core` it is one solid line (hover). With `core` (the segment's score colour) it is the selection: a
 * soft glow, an outline in `color`, a white gap, the score colour kept inside it (the same as the marker ring), and white
 * dashes flowing along it, like traffic in the lane (still under prefers-reduced-motion, see .cc-flow).
 */
function SegmentHighlight({
  point,
  color,
  weight,
  core,
}: {
  point?: MapPointInfo;
  color: string;
  weight: number;
  core?: string;
}) {
  const map = useMap();
  const [zoom, setZoom] = useState(() => map.getZoom());
  useMapEvent("zoomend", () => setZoom(map.getZoom()));
  if (point?.kind !== "segment") return null;
  const w = Math.round(
    clamp(weight - (FOCUS_ZOOM - zoom) * 4, LANE_PX + 2, weight),
  );
  const line = (key: string, options: L.PathOptions) => (
    <Polyline
      key={key}
      positions={point.wgs}
      pathOptions={{
        opacity: 1,
        lineCap: "round",
        lineJoin: "round",
        ...options,
      }}
      interactive={false}
    />
  );
  if (!core) return line("solid", { color, weight: w });

  // Leaflet stacks lines in a pane in the order they are added, so these are always rendered in this order.
  const coreW = Math.max(3, Math.round(w * 0.45));
  // A white gap between the outline and the score colour, like the marker's white border: indigo right against
  // the dark scores buzzed. Zoomed out there is no room for it next to a visible outline; it is hidden then.
  const gapShown = w - coreW >= 8;
  return (
    <>
      {line("glow", { color, weight: w + GLOW_PX, opacity: 0.22 })}
      {line("casing", { color, weight: w })}
      {line("gap", {
        color: "#fff",
        weight: coreW + 4,
        opacity: gapShown ? 1 : 0,
      })}
      {line("core", { color: core, weight: coreW })}
      {line("flow", {
        color: "#fff",
        weight: 2.5,
        dashArray: "3 9",
        className: "cc-flow",
        // with too thin a core the dashes would crowd it: hide them (kept mounted, so the stacking order holds)
        opacity: coreW >= FLOW_MIN_CORE_PX ? 0.95 : 0,
      })}
    </>
  );
}

/** Pane of the street network's score lines. */
const TRAILS_PANE = "trails";
/** Width of the invisible line over each score line that takes its clicks: easier to hit than the thin score line. */
const HIT_LINE_PX = 20;

/** A street piece's tooltip as a DOM node (street names are shown as text, never parsed as HTML). */
function segmentTooltip(
  p: MapPointInfo,
  r: PointResult | undefined,
  metric: MetricId,
): HTMLElement {
  const el = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = pointTitle(p);
  el.append(
    title,
    document.createElement("br"),
    `${METRIC_SHORT[metric]} score ${r ? dec2(r.scores[metric]) : "…"}`,
  );
  return el;
}

/**
 * The street network's score lines: the bulk of the map (~1800 pieces, each with a hit line). They are plain Leaflet
 * layers, not react-leaflet components: as components, every render of the map (a hover in the worst list, a
 * selection) re-rendered and restyled all ~3600 of them, which froze the page for a moment. Here they are built once
 * per data load, and only the lines whose colour or width changes are restyled.
 *
 * They stay SVG (not canvas, which would draw faster): a canvas takes every pointer event over the whole map, so
 * the parks and oasis outlines in the panes below would lose their tooltips. Leaflet's SVG lets events through
 * everywhere except on the (hit) lines.
 */
const NetworkLines = memo(function NetworkLines({
  segments,
  results,
  metric,
  muted,
  keepId,
  onSelect,
}: {
  segments: readonly MapPointInfo[];
  results: ReadonlyMap<string, PointResult>;
  metric: MetricId;
  /** Street pieces are left out of "Where to look": drawn grey and thinner, still clickable. */
  muted: boolean;
  /** The selected piece keeps its colours even when muted (it can be picked from the plan). */
  keepId?: string;
  onSelect: (id: string) => void;
}) {
  const map = useMap();
  // the class bounds array is stable (from context), unlike a colour function made per render
  const { breaks } = useScoreScale(metric);
  const [zoom, setZoom] = useState(() => map.getZoom());
  useMapEvent("zoomend", () => setZoom(map.getZoom()));
  const laneWidth = clamp(LANE_PX - (FOCUS_ZOOM - zoom), LANE_MIN_PX, LANE_PX);
  const lines = useRef(
    new Map<string, { line: L.Polyline; hit: L.Polyline }>(),
  );
  // The click handlers and tooltips are bound once, so they read the current values from here.
  const live = useRef({ results, metric, onSelect });
  useLayoutEffect(() => {
    live.current = { results, metric, onSelect };
  });

  useEffect(() => {
    const byId = lines.current;
    const scoreLines = L.layerGroup();
    const hitLines = L.layerGroup();
    for (const p of segments) {
      const line = L.polyline(p.wgs, {
        pane: TRAILS_PANE,
        opacity: 1,
        lineCap: "butt",
        interactive: false,
      });
      const hit = L.polyline(p.wgs, {
        pane: TRAILS_PANE,
        color: "#000",
        weight: HIT_LINE_PX,
        opacity: 0,
        // keep the click off the map, where it would close the details popup it is about to open
        bubblingMouseEvents: false,
      });
      hit.on("click", () => live.current.onSelect(p.id));
      hit.bindTooltip(
        () =>
          segmentTooltip(
            p,
            live.current.results.get(p.id),
            live.current.metric,
          ),
        {
          sticky: true,
          className: "cc-tooltip",
          direction: "top",
          offset: [0, -8],
        },
      );
      scoreLines.addLayer(line);
      hitLines.addLayer(hit);
      byId.set(p.id, { line, hit });
    }
    // the hit lines after (so above) every score line, or a neighbour's score line would cover them
    scoreLines.addTo(map);
    hitLines.addTo(map);
    return () => {
      scoreLines.remove();
      hitLines.remove();
      byId.clear();
    };
  }, [map, segments]);

  // Colours and widths. Also re-run for new `segments`: the lines above were rebuilt with Leaflet's default style.
  useEffect(() => {
    const neutral = cssVar("--color-network");
    for (const [id, { line, hit }] of lines.current) {
      const r = results.get(id);
      const off = muted && id !== keepId;
      const color = r && !off ? colorFor(r.scores[metric], breaks) : neutral;
      const weight = off
        ? Math.max(MUTED_LANE_MIN_PX, laneWidth * MUTED_LANE_SHARE)
        : laneWidth;
      if (line.options.color !== color || line.options.weight !== weight)
        line.setStyle({ color, weight });
      // a tooltip open under the pointer shows the new score right away
      if (hit.isTooltipOpen()) hit.getTooltip()?.update();
    }
  }, [segments, results, metric, muted, keepId, breaks, laneWidth]);

  return null;
});

export default function MapView({
  mapData,
  evaluation,
  metric,
  kinds,
  worstId,
  selectedId,
  hoveredId,
  onSelect,
  focusRequest,
  drawerOverMap,
  popup,
  onClosePopup,
}: Props) {
  const popupRef = useRef<L.Popup>(null);
  const [map, setMap] = useState<L.Map | null>(null);
  const [showPlan, setShowPlan] = useState(true);
  const [showFountains, setShowFountains] = useState(false);
  const [showShade, setShowShade] = useState(false);
  const [showBikeParking, setShowBikeParking] = useState(false);

  const results = useMemo(
    () => new Map(evaluation?.points.map((p) => [p.id, p])),
    [evaluation],
  );
  const bounds = useMemo(
    () => L.latLngBounds(mapData.points.flatMap((p) => p.wgs)).pad(0.3),
    [mapData.points],
  );
  const segments = useMemo(
    () => mapData.points.filter((p) => p.kind === "segment"),
    [mapData.points],
  );
  const nodes = useMemo(
    () =>
      mapData.points.filter(
        (p): p is MapPointInfo & { kind: "junction" | "station" } =>
          p.kind !== "segment",
      ),
    [mapData.points],
  );
  const pointsById = useMemo(
    () => new Map(mapData.points.map((p) => [p.id, p])),
    [mapData.points],
  );
  const worstPoint = worstId ? pointsById.get(worstId) : undefined;
  // The selected point keeps its colours even when its kind is filtered out (it can be picked from the plan).
  const muted = (p: MapPointInfo) => !kinds.has(p.kind) && p.id !== selectedId;
  const selected = selectedId ? pointsById.get(selectedId) : undefined;
  const hovered = hoveredId ? pointsById.get(hoveredId) : undefined;
  // Reach drawn around fountains and oases: the distance where the water score hits 1 (worst). Outside the circle
  // the water score is 1; inside it the score falls to 0 within water_ok_m.
  const waterReach = Number(
    mapData.assumptions.find((a) => a.key === "water_bad_m")?.value ?? 0,
  );
  // Reach drawn around oases (shade to rest in): the same "short detour" as for water. Parks: PARK_SHADE_REACH_M.
  const shadeReach = Number(
    mapData.assumptions.find((a) => a.key === "water_ok_m")?.value ?? 0,
  );

  const fixesByPoint = useMemo(() => {
    const m = new Map<string, Evaluation["plan"]>();
    for (const f of evaluation?.plan ?? [])
      m.set(f.point_id, [...(m.get(f.point_id) ?? []), f]);
    return m;
  }, [evaluation]);

  const scoreColor = useScoreScale(metric).color;
  const neutral = cssVar("--color-network");
  const water = cssVar("--color-water");
  const park = cssVar("--color-park");
  const selection = cssVar("--color-selection");
  const selectionHover = cssVar("--color-selection-hover");
  const selectedResult = selected ? results.get(selected.id) : undefined;
  const selectedCore = selectedResult
    ? scoreColor(selectedResult.scores[metric])
    : neutral;

  return (
    <div className="@container relative h-full w-full">
      <MapContainer
        ref={setMap}
        bounds={bounds}
        className="h-full w-full"
        zoomSnap={0.5}
        scrollWheelZoom
        preferCanvas={false}
        attributionControl={false}
      >
        {/* Leaflet's default prefix also carries a flag; keep only the Leaflet credit (open-source licences must be credited).
            One OSM credit covers both the basemap and the park outlines (ODbL terms are on the linked copyright page). */}
        <AttributionControl prefix='<a href="https://leafletjs.com">Leaflet</a>' />
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          className="cc-basemap"
          maxZoom={19}
        />
        {selected && popup && (
          <PointPopup
            key={selected.id}
            point={selected}
            popupRef={popupRef}
            onClose={onClosePopup}
          >
            {popup}
          </PointPopup>
        )}
        <FollowLayout
          point={selected}
          drawerOverMap={drawerOverMap}
          focusRequest={focusRequest}
          popupRef={popupRef}
        />

        {/* Shade reach under the parks: drawn opaque and the pane faded as a whole, so overlapping parks and oases
            merge into one evenly tinted area. */}
        <Pane
          name="shade-reach"
          style={{ zIndex: 384, opacity: SHADE_REACH_OPACITY }}
        >
          {showShade && shadeReach > 0 && (
            <>
              <ParkReach
                parks={mapData.parks}
                radius={PARK_SHADE_REACH_M}
                color={park}
              />
              {evaluation?.oases.map((o) => (
                <Circle
                  key={`shade-${o.point_id}`}
                  center={o.wgs}
                  radius={shadeReach}
                  interactive={false}
                  pathOptions={{
                    stroke: false,
                    fillColor: park,
                    fillOpacity: 1,
                  }}
                />
              ))}
            </>
          )}
        </Pane>

        {/* Parks under the reach tint and the trails, so they never take a click meant for a trail piece. */}
        <Pane name="parks" style={{ zIndex: 385 }}>
          {showShade &&
            evaluation?.oases.map((o) => (
              <Circle
                key={`shade-outline-${o.point_id}`}
                center={o.wgs}
                radius={shadeReach}
                pathOptions={{
                  color: park,
                  weight: 1.5,
                  dashArray: "4 4",
                  fill: false,
                }}
              >
                <Tooltip className="cc-tooltip" sticky>
                  <strong>Cyclist Oasis · in your plan</strong>
                  <br />
                  Shade within {metres(shadeReach)}
                </Tooltip>
              </Circle>
            ))}
          {showShade && (
            <GeoJSON
              data={mapData.parks}
              style={{
                color: park,
                weight: 1,
                opacity: 0.7,
                fillColor: park,
                fillOpacity: 0.22,
              }}
              onEachFeature={(f, layer) =>
                layer.bindTooltip(parkTooltip(f.properties as ParkProps), {
                  className: "cc-tooltip",
                  sticky: true,
                })
              }
            />
          )}
        </Pane>

        {/* Reach fills are drawn opaque and the pane is faded as a whole, so overlapping circles merge into one
            evenly tinted area instead of getting darker with every overlap (per-circle fillOpacity would stack). */}
        <Pane name="reach" style={{ zIndex: 390, opacity: REACH_OPACITY }}>
          {showFountains &&
            mapData.fountains.map((f) => (
              <Circle
                key={f.id}
                center={f.wgs}
                radius={waterReach}
                interactive={false}
                pathOptions={{
                  stroke: false,
                  fillColor: water,
                  fillOpacity: 1,
                }}
              />
            ))}
          {showPlan &&
            evaluation?.oases.map((o) => (
              <Circle
                key={`oasis-${o.point_id}`}
                center={o.wgs}
                radius={waterReach}
                interactive={false}
                pathOptions={{
                  stroke: false,
                  fillColor: water,
                  fillOpacity: 1,
                }}
              />
            ))}
        </Pane>
        {/* Oasis outlines in a pane of their own so the reach pane's fade doesn't wash them out. */}
        <Pane name="reach-outline" style={{ zIndex: 391 }}>
          {showPlan &&
            evaluation?.oases.map((o) => (
              <Circle
                key={`oasis-outline-${o.point_id}`}
                center={o.wgs}
                radius={waterReach}
                interactive={false}
                pathOptions={{
                  color: water,
                  weight: 1.5,
                  dashArray: "4 4",
                  fill: false,
                }}
              />
            ))}
        </Pane>

        <Pane name={TRAILS_PANE} style={{ zIndex: 410 }}>
          <NetworkLines
            segments={segments}
            results={results}
            metric={metric}
            muted={!kinds.has("segment")}
            keepId={selectedId}
            onSelect={onSelect}
          />
        </Pane>

        {/* Highlights get panes of their own above the lines: Leaflet stacks lines within a pane in the order they
            were added, so a highlight added before its neighbours would end up under them. */}
        <Pane name="hovered" style={{ zIndex: 412 }}>
          {hovered?.id !== selected?.id && (
            <SegmentHighlight
              point={hovered}
              color={selectionHover}
              weight={HOVERED_LINE_PX}
            />
          )}
        </Pane>
        <Pane name="selected" style={{ zIndex: 414 }}>
          <SegmentHighlight
            point={selected}
            color={selection}
            weight={SELECTED_LINE_PX}
            core={selectedCore}
          />
        </Pane>

        {/* Above the trail lines, under the junction and station markers (Leaflet's marker pane, 600). */}
        <Pane name="fountains" style={{ zIndex: 420 }}>
          {showFountains &&
            mapData.fountains.map((f) => (
              <Marker
                key={f.id}
                position={f.wgs}
                icon={fountainIcon}
                keyboard={false}
              >
                <Tooltip
                  className="cc-tooltip"
                  direction="top"
                  offset={[0, -10]}
                >
                  Drinking fountain{f.location ? ` · ${f.location}` : ""}
                </Tooltip>
              </Marker>
            ))}
          {showBikeParking &&
            mapData.bike_parkings.map((b) => (
              <Marker
                key={b.id}
                position={b.wgs}
                icon={bikeParkingIcon}
                keyboard={false}
              >
                <Tooltip
                  className="cc-tooltip"
                  direction="top"
                  offset={[0, -8]}
                >
                  <strong>
                    Bicibox bike parking{b.name ? ` · ${b.name}` : ""}
                  </strong>
                  {b.address && (
                    <>
                      <br />
                      {b.address}
                    </>
                  )}
                </Tooltip>
              </Marker>
            ))}
        </Pane>

        {nodes.map((p) => {
          const r = results.get(p.id);
          const off = muted(p);
          const color = r && !off ? scoreColor(r.scores[metric]) : neutral;
          const highlight =
            p.id === selectedId
              ? "selected"
              : p.id === hoveredId
                ? "hovered"
                : undefined;
          return (
            <Marker
              key={p.id}
              position={p.mid_wgs}
              icon={nodeIcon(p.kind, color, highlight, off)}
              eventHandlers={{ click: () => onSelect(p.id) }}
              keyboard
              title={pointTitle(p)}
              // the highlighted marker's ring sits above its neighbours (but under the fix badges at 500), and
              // greyed-out markers sit under the ones in play
              zIndexOffset={
                (p.kind === "station" ? 100 : 0) +
                (highlight === "selected" ? 300 : highlight ? 200 : 0) -
                (off ? 300 : 0)
              }
            >
              <Tooltip className="cc-tooltip" direction="top" offset={[0, -14]}>
                <strong>{pointTitle(p)}</strong>
                <br />
                {METRIC_SHORT[metric]} score {r ? dec2(r.scores[metric]) : "…"}
                <br />
                {p.kind === "junction" ? (
                  <span style={{ color: "var(--color-warning)" }}>
                    {p.located_by ?? "Approximate location"} · synthetic point,
                    moved {metres(p.snap_distance_m)}
                  </span>
                ) : (
                  <>
                    Real AMBici station
                    {isOffTrail(p) && (
                      <>
                        , {metres(p.trail_dist_m)} off the trails
                        <br />
                        <span style={{ color: "var(--color-warning)" }}>
                          Heat from the nearest street
                        </span>
                      </>
                    )}
                  </>
                )}
              </Tooltip>
            </Marker>
          );
        })}

        {showPlan &&
          [...fixesByPoint.entries()].flatMap(([pid, fixes]) => {
            const p = pointsById.get(pid);
            // Clicking a fix selects its point, which also highlights the fix in "Your plan".
            return p
              ? fixes.map((f, slot) => (
                  <Marker
                    key={`fix-${pid}-${f.fix_id}`}
                    position={p.mid_wgs}
                    icon={fixBadge(f.fix_id, slot)}
                    eventHandlers={{ click: () => onSelect(pid) }}
                    keyboard
                    alt={`${f.label} at ${pointTitle(p)}, in your plan`}
                    zIndexOffset={500}
                  >
                    <Tooltip
                      className="cc-tooltip"
                      direction="top"
                      // just above the badge (see fixBadge's iconAnchor)
                      offset={[slot * 20, -36]}
                    >
                      <strong>{f.label}</strong>
                      <br />
                      In your plan · {pointTitle(p)}
                    </Tooltip>
                  </Marker>
                ))
              : [];
          })}

        {worstPoint && (
          <Marker
            position={worstPoint.mid_wgs}
            icon={worstRing}
            interactive={false}
            zIndexOffset={-100}
          />
        )}
      </MapContainer>

      {worstPoint && (
        <button
          type="button"
          data-map-overlay
          onClick={() => onSelect(worstPoint.id)}
          className="absolute left-14 top-3 z-[1000] inline-flex min-h-10 items-center gap-2 rounded-lg border border-border bg-surface px-3 text-sm font-semibold text-primary shadow-sm hover:bg-primary-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <Target className="size-4" aria-hidden />
          Go to worst point
        </button>
      )}

      {map && (
        <button
          type="button"
          data-map-overlay
          onClick={() => {
            const animate = !window.matchMedia(
              "(prefers-reduced-motion: reduce)",
            ).matches;
            if (animate) map.flyToBounds(bounds, { duration: 0.8 });
            else map.fitBounds(bounds, { animate: false });
          }}
          title="Back to the default view"
          aria-label="Back to the default view"
          className="absolute bottom-8 right-3 z-[1000] inline-flex size-10 items-center justify-center rounded-lg border border-border bg-surface text-primary shadow-sm hover:bg-primary-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <House className="size-4" aria-hidden />
        </button>
      )}

      {/* layer toggles */}
      <fieldset
        data-map-overlay
        className="absolute right-3 top-3 z-[1000] hidden rounded-xl border border-border bg-surface/95 px-3 py-2 text-xs shadow-sm backdrop-blur md:block"
      >
        <legend className="sr-only">Map layers</legend>
        {[
          {
            label: "Fixes in the plan",
            checked: showPlan,
            set: setShowPlan,
          },
          {
            label: `Shade spots (parks and oases)`,
            checked: showShade,
            set: setShowShade,
          },
          {
            label: "Drinking fountains",
            checked: showFountains,
            set: setShowFountains,
          },
          {
            label: "Bicibox bike parkings ",
            checked: showBikeParking,
            set: setShowBikeParking,
          },
        ].map((o) => (
          <label
            key={o.label}
            className="flex cursor-pointer items-center gap-2 py-0.5"
          >
            <input
              type="checkbox"
              checked={o.checked}
              onChange={(e) => o.set(e.target.checked)}
              className="accent-primary"
            />
            {o.label}
          </label>
        ))}
      </fieldset>

      {/* On a map too narrow for both (popup 360 + legend 208 + gaps), the open popup wins over the legend. */}
      <div className={selected && popup ? "@max-[38rem]:hidden" : undefined}>
        <Legend metric={metric} filtered={kinds.size < 3} />
      </div>
    </div>
  );
}
