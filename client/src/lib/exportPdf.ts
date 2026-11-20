/**
 * The plan report: a PDF with what the accepted fixes change on the trail network and where each fix goes.
 * Built in the browser from the evaluation on screen, so every number is the one the planner sees.
 * Loaded on demand (dynamic import) to keep jsPDF out of the main bundle.
 */
import { jsPDF } from "jspdf";
import {
  autoTable,
  type CellDef,
  type CellHookData,
  type RowInput,
  type UserOptions,
} from "jspdf-autotable";
import type {
  Assumption,
  Evaluation,
  MapData,
  MapPointInfo,
  Trail,
} from "../api/planner.ts";
import { celsius, DASH, dec1, dec2, eur, int, km, metres } from "./format.ts";
import { isOffTrail, pointTitle } from "./points.ts";

type Rgb = [number, number, number];

// Same values as src/theme/colors.css (the PDF can't read CSS variables).
const PRIMARY: Rgb = [15, 94, 99];
const PRIMARY_SOFT: Rgb = [226, 238, 237];
const FOREGROUND: Rgb = [15, 23, 42];
const MUTED: Rgb = [91, 102, 112];
const BORDER: Rgb = [227, 225, 218];
const SURFACE_2: Rgb = [249, 248, 245];
const GAIN: Rgb = [0, 122, 47];
const WATER: Rgb = [42, 120, 214];

// A4 portrait, in mm.
const PAGE_W = 210;
const PAGE_H = 297;
const M = 14;
const CONTENT_W = PAGE_W - 2 * M;
const FOOTER_Y = PAGE_H - 8;
const BOTTOM = PAGE_H - 18;

/**
 * The built-in PDF fonts only cover WinAnsi (Latin-1 plus a few typographic marks), and one character outside it
 * garbles the whole line. Street names are Latin-1; this catches the odd symbol (CO₂, arrows) that isn't.
 * "€" is in WinAnsi, but the standard Helvetica metrics viewers use have no width for it, so it overprints the
 * next digit (seen in macOS Preview): amounts are written "EUR 1,234" instead.
 */
const WIN_ANSI_EXTRA = "‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ";
const REPLACE: Record<string, string> = {
  "€": "EUR ",
  "₂": "2",
  "→": "->",
  "≥": ">=",
  "≤": "<=",
  "≈": "~",
  "−": "-",
};

export function pdfText(s: string): string {
  let out = "";
  for (const ch of s) {
    if (ch.codePointAt(0)! < 0x100 || WIN_ANSI_EXTRA.includes(ch)) out += ch;
    else out += REPLACE[ch] ?? (/\s/.test(ch) ? " " : "?");
  }
  return out;
}

const fmtAssumption = (a: Assumption) =>
  Array.isArray(a.value)
    ? a.value.join(", ")
    : a.unit === "share" && typeof a.value === "number"
      ? `${Math.round(a.value * 100)} %`
      : `${a.value} ${a.unit}`.trim();

const pctOf = (part: number, total: number) =>
  total > 0 ? `${dec1((part / total) * 100)}%` : DASH;

/** A "change" cell: green and bold when the plan improved the value. */
const change = (text: string, improved: boolean): CellDef =>
  improved
    ? { content: text, styles: { textColor: GAIN, fontStyle: "bold" } }
    : { content: text, styles: { textColor: MUTED } };

function coverageRow(
  label: string,
  before: number,
  after: number,
  total: number,
): RowInput {
  const gain = after - before;
  const pp = total > 0 ? (gain / total) * 100 : 0;
  const changed = Math.abs(gain) >= 0.005;
  return [
    label,
    `${km(before)} (${pctOf(before, total)})`,
    `${km(after)} (${pctOf(after, total)})`,
    change(
      changed
        ? `${gain > 0 ? "+" : ""}${dec2(gain)} km (${pp > 0 ? "+" : ""}${dec1(pp)} pp)`
        : "no change",
      gain >= 0.005,
    ),
  ];
}

function placeDetail(p: MapPointInfo): string {
  if (p.kind === "segment")
    return `Street piece ${p.id} · ${metres(p.length_m)} long`;
  if (p.kind === "junction")
    return `Traffic-light junction ${p.id} · approximate location`;
  const off = isOffTrail(p)
    ? ` · ${Math.round(p.trail_dist_m ?? 0)} m off the trail`
    : "";
  return `AMBici bike station${p.address ? ` · ${p.address}` : ""}${off}`;
}

const osmUrl = ([lat, lng]: [number, number]) =>
  `https://www.openstreetmap.org/?mlat=${lat.toFixed(6)}&mlon=${lng.toFixed(6)}#map=19/${lat.toFixed(6)}/${lng.toFixed(6)}`;

const localDate = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const finalY = (doc: jsPDF) =>
  (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable
    .finalY;

/** Table defaults shared by every table in the report. */
function table(doc: jsPDF, startY: number, opts: UserOptions) {
  const { styles, didParseCell: userParse, ...rest } = opts;
  autoTable(doc, {
    startY,
    margin: { top: 16, bottom: PAGE_H - BOTTOM, left: M, right: M },
    theme: "grid",
    headStyles: {
      fillColor: PRIMARY_SOFT,
      textColor: PRIMARY,
      fontStyle: "bold",
      fontSize: 8,
    },
    footStyles: {
      fillColor: SURFACE_2,
      textColor: FOREGROUND,
      fontStyle: "bold",
    },
    alternateRowStyles: { fillColor: SURFACE_2 },
    rowPageBreak: "avoid",
    ...rest,
    styles: {
      font: "helvetica",
      fontSize: 8.5,
      cellPadding: 1.8,
      textColor: FOREGROUND,
      lineColor: BORDER,
      lineWidth: 0.2,
      valign: "middle",
      ...styles,
    },
    didParseCell: (data: CellHookData) => {
      data.cell.text = data.cell.text.map(pdfText);
      userParse?.(data);
    },
  });
  return finalY(doc);
}

/** Starts a new page when fewer than `needed` mm are left, so a heading never sits alone at the bottom. */
function ensureSpace(doc: jsPDF, y: number, needed: number) {
  if (y + needed <= BOTTOM) return y;
  doc.addPage();
  return 18;
}

function heading(doc: jsPDF, y: number, text: string, sub?: string) {
  y = ensureSpace(doc, y, 30);
  doc
    .setFont("helvetica", "bold")
    .setFontSize(12.5)
    .setTextColor(...PRIMARY);
  doc.text(pdfText(text), M, y);
  if (!sub) return y + 3.5;
  doc
    .setFont("helvetica", "normal")
    .setFontSize(8.5)
    .setTextColor(...MUTED);
  const lines = doc.splitTextToSize(pdfText(sub), CONTENT_W);
  doc.text(lines, M, y + 5);
  return y + 5 + lines.length * 3.6;
}

function note(doc: jsPDF, y: number, text: string) {
  doc
    .setFont("helvetica", "normal")
    .setFontSize(7.5)
    .setTextColor(...MUTED);
  const lines = doc.splitTextToSize(pdfText(text), CONTENT_W);
  y = ensureSpace(doc, y, lines.length * 3.3 + 2);
  doc.text(lines, M, y + 3);
  return y + 3 + lines.length * 3.3;
}

export type PlanReportInput = {
  mapData: MapData;
  evaluation: Evaluation;
  pointsById: ReadonlyMap<string, MapPointInfo>;
  trailsById: ReadonlyMap<string, Trail>;
  now?: Date;
};

export function buildPlanPdf({
  mapData,
  evaluation: ev,
  pointsById,
  trailsById,
  now = new Date(),
}: PlanReportInput): jsPDF {
  const doc = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait" });
  const k = ev.kpis;
  const assumption = (key: string) =>
    mapData.assumptions.find((a) => a.key === key)?.value;
  const comfortC = assumption("comfortable_utci_c");
  const strongHeatC = assumption("strong_heat_utci_c");
  const waterM = assumption("water_ok_m");
  const adaptedC = assumption("adapted_min_utci_drop_c");
  const metricLabel =
    mapData.metrics.find((m) => m.id === ev.metric)?.label ?? ev.metric;
  const catalogue = new Map(mapData.catalogue.map((c) => [c.id, c]));
  const generated = new Intl.DateTimeFormat("en-GB", {
    dateStyle: "long",
    timeStyle: "short",
  }).format(now);
  const title = "Heat-comfort plan for Viladecans cycle trails";

  doc.setProperties({
    title,
    subject:
      "Where to place the planned summer-cycling fixes and what they change",
    creator: "CoolCycle",
  });

  // ---- Title band ----
  doc.setFillColor(...PRIMARY).rect(0, 0, PAGE_W, 31, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold").setFontSize(8.5).text("COOLCYCLE", M, 10);
  doc.setFontSize(17).text(title, M, 19);
  doc.setFont("helvetica", "normal").setFontSize(9);
  doc.text(
    pdfText(
      `Generated ${generated} · fixes chosen by the ${metricLabel.toLowerCase()} ranking`,
    ),
    M,
    26,
  );

  let y = 42;
  const r = ev.burden.reduction_pct;

  // ---- 1. Impact ----
  y = heading(
    doc,
    y,
    "1. What the plan changes",
    'Recalculated from the accepted fixes over all street pieces, junctions and bike stations. "Today" is the network with no fix applied.',
  );
  y = table(doc, y + 1, {
    head: [["Indicator", "Today", "With the plan", "Change"]],
    body: [
      [
        `${metricLabel} burden (score x riders x time spent, today = 100)`,
        r == null ? DASH : "100",
        r == null ? DASH : dec1(100 - r),
        r == null
          ? DASH
          : change(r >= 0.05 ? `-${dec1(r)}%` : "no change", r >= 0.05),
      ],
      coverageRow(
        `Comfortable km (UTCI below ${comfortC ?? "?"} °C, warm summer day)`,
        k.before.comfortable_km,
        k.after.comfortable_km,
        k.after.network_km,
      ),
      coverageRow(
        `Out of very strong heat (UTCI below ${strongHeatC ?? "?"} °C, heatwave day)`,
        k.before.below_strong_heat_km,
        k.after.below_strong_heat_km,
        k.after.network_km,
      ),
      coverageRow(
        `Drinking water within ${waterM ?? "?"} m`,
        k.before.water_reachable_km,
        k.after.water_reachable_km,
        k.after.network_km,
      ),
    ],
    columnStyles: {
      0: { cellWidth: 70 },
      1: { cellWidth: 36 },
      2: { cellWidth: 36 },
      3: { cellWidth: 40 },
    },
  });

  const cooled = k.utci_drop_trail_avg_c != null;
  y = table(doc, y + 4, {
    head: [["Cooling, climate and cost", "With the plan"]],
    body: [
      [
        "Average UTCI drop where the plan cools",
        cooled
          ? `-${celsius(k.utci_drop_trail_avg_c)} on ${km(k.utci_cooled_trail_km)} of ${km(k.after.network_km)} of network`
          : "no trail section cooled",
      ],
      [
        "UTCI drop at critical points (junctions + hottest 10%; average over all)",
        k.critical_drop_avg_c == null
          ? `0.0 °C (none of ${int(k.critical_total)} cooled)`
          : `-${celsius(k.critical_drop_avg_c)}; -${celsius(k.critical_drop_cooled_avg_c)} at the ${int(k.critical_cooled)} of ${int(k.critical_total)} cooled, max -${celsius(k.critical_drop_max_c)}`,
      ],
      [
        "Summer cyclists won back",
        `${dec1(k.new_summer_cyclists)} cyclists (${dec1(k.recovered_trips_per_day)} trips per day)`,
      ],
      [
        "CO2 avoided by replaced trips",
        `${dec2(k.co2_trips_t_per_year)} t CO2e per year (plus ${dec2(k.co2_sequestration_t_per_year)} t trees and oases, ${dec2(k.co2_pv_avoided_t_per_year)} t solar canopies; total ${dec2(k.co2_t_per_year)} t)`,
      ],
      ["Investment (one-off)", eur(k.capex_eur)],
      ["Yearly upkeep", `${eur(k.opex_eur_per_year)} per year`],
      [
        `Cost per km adapted (trees, cool pavement; cooled by ${adaptedC ?? "?"} °C or more)`,
        k.eur_per_adapted_km == null
          ? `${DASH} (no street piece cooled enough by trees or cool pavement)`
          : `${eur(k.eur_per_adapted_km)} per km on ${km(k.adapted_km)}`,
      ],
      [
        "Cost per km made comfortable (whole plan)",
        k.eur_per_comfortable_km == null
          ? `${DASH} (no km made comfortable)`
          : eur(k.eur_per_comfortable_km),
      ],
      [
        "Cost per summer cyclist won back",
        k.eur_per_new_cyclist_year == null
          ? DASH
          : `${eur(k.eur_per_new_cyclist_year)} per year (investment over service life + upkeep); ${eur(k.eur_per_new_cyclist ?? 0)} one-off`,
      ],
      [
        "Saved per cyclist per year on travel",
        `${eur(k.eur_saved_per_cyclist_year)} on average; ${eur(k.eur_saved_car_switcher_year)} for one who leaves the car`,
      ],
      [
        "Saved by all new cyclists per year",
        eur(k.eur_saved_total_year),
      ],
    ],
    columnStyles: { 0: { cellWidth: 82 }, 1: { cellWidth: 100 } },
  });
  y += 9;

  // ---- 2. Where ----
  y = heading(
    doc,
    y,
    "2. Where to put the fixes",
    "Fix types in the plan, then every fix with its place, in the order they were accepted.",
  );
  const byFix = new Map<
    string,
    {
      label: string;
      places: number;
      lengthM: number;
      cost: number;
      opex: number;
    }
  >();
  for (const f of ev.plan) {
    const g = byFix.get(f.fix_id) ?? {
      label: f.label,
      places: 0,
      lengthM: 0,
      cost: 0,
      opex: 0,
    };
    g.places += 1;
    g.lengthM += pointsById.get(f.point_id)?.length_m ?? 0;
    g.cost += f.cost_eur;
    g.opex += f.opex_eur_yr;
    byFix.set(f.fix_id, g);
  }
  y = table(doc, y + 1, {
    head: [["Fix", "Places", "Trail length", "Investment", "Upkeep / yr"]],
    body: [...byFix.entries()]
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .map(([id, g]) => [
        `${g.label} (${id})`,
        int(g.places),
        catalogue.get(id)?.priced_per_m ? metres(g.lengthM) : DASH,
        eur(g.cost),
        eur(g.opex),
      ]),
    foot: [
      [
        "Total",
        int(ev.plan.length),
        "",
        eur(ev.budget.spent),
        eur(k.opex_eur_per_year),
      ],
    ],
    columnStyles: {
      0: { cellWidth: 82 },
      1: { cellWidth: 20, halign: "right" },
      2: { cellWidth: 26, halign: "right" },
      3: { cellWidth: 27, halign: "right" },
      4: { cellWidth: 27, halign: "right" },
    },
    didParseCell: (d) => {
      if (d.section !== "body" && d.column.index > 0)
        d.cell.styles.halign = "right";
    },
  });

  const COORD_COL = 4;
  const links = ev.plan.map((f) => {
    const p = pointsById.get(f.point_id);
    return p ? osmUrl(p.mid_wgs) : undefined;
  });
  // Room for the header and a first row, or the header would sit alone at the bottom of the page.
  y = table(doc, ensureSpace(doc, y + 4, 24), {
    head: [["#", "Fix", "Place", "Trail", "Coordinates", "Cost"]],
    body: ev.plan.map((f, i) => {
      const p = pointsById.get(f.point_id);
      const trail = p?.trail_id ? trailsById.get(p.trail_id) : undefined;
      return [
        String(i + 1),
        `${f.label}\n${f.fix_id}`,
        p ? `${pointTitle(p)}\n${placeDetail(p)}` : f.point_id,
        trail ? trail.name : DASH,
        p
          ? {
              content: `${p.mid_wgs[0].toFixed(5)}, ${p.mid_wgs[1].toFixed(5)}\nOpen in map`,
              styles: { textColor: WATER },
            }
          : DASH,
        `${eur(f.cost_eur)}\n+${eur(f.opex_eur_yr)}/yr`,
      ];
    }),
    styles: { fontSize: 8, valign: "top" },
    columnStyles: {
      0: { cellWidth: 7, halign: "right" },
      1: { cellWidth: 38 },
      2: { cellWidth: 56 },
      3: { cellWidth: 31 },
      4: { cellWidth: 27 },
      5: { cellWidth: 23, halign: "right" },
    },
    didDrawCell: (d) => {
      const url =
        d.section === "body" && d.column.index === COORD_COL
          ? links[d.row.index]
          : undefined;
      if (url)
        doc.link(d.cell.x, d.cell.y, d.cell.width, d.cell.height, { url });
    },
  });
  y = note(
    doc,
    y + 1,
    "Coordinates are WGS84 latitude, longitude at the middle of each place; click them to open the spot in OpenStreetMap. Junctions are placed at the real crossing or facility their VAS-R1 name refers to (the synthetic coordinates are 140-850 m off). Trees and cool pavement are priced per 100 m and laid along the whole real street segment, so their cost follows its length.",
  );
  y += 8;

  // ---- 3. Assumptions ----
  y = heading(
    doc,
    y,
    "3. Assumptions behind the numbers",
    "Change any of them in the model and every number above is recalculated.",
  );
  table(doc, y + 1, {
    head: [["Assumption", "Value", "Source", "Why"]],
    body: mapData.assumptions.map((a) => [
      a.label,
      fmtAssumption(a),
      a.source,
      a.note,
    ]),
    styles: { fontSize: 7.5, valign: "top" },
    columnStyles: {
      0: { cellWidth: 46, fontStyle: "bold" },
      1: { cellWidth: 30 },
      2: { cellWidth: 24 },
      3: { cellWidth: 82, textColor: MUTED },
    },
  });

  // ---- Footer on every page ----
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc
      .setDrawColor(...BORDER)
      .setLineWidth(0.2)
      .line(M, FOOTER_Y - 4, PAGE_W - M, FOOTER_Y - 4);
    doc
      .setFont("helvetica", "normal")
      .setFontSize(7.5)
      .setTextColor(...MUTED);
    doc.text(
      "CoolCycle · synthetic VAS-R1 demo data, not real Viladecans measurements",
      M,
      FOOTER_Y,
    );
    doc.text(`Page ${i} of ${pages}`, PAGE_W - M, FOOTER_Y, { align: "right" });
  }
  return doc;
}

/** Builds the report and hands it to the browser as a download. */
export function exportPlanPdf(input: PlanReportInput) {
  const now = input.now ?? new Date();
  buildPlanPdf({ ...input, now }).save(`coolcycle-plan-${localDate(now)}.pdf`);
}
