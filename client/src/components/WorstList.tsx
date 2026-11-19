import { useState } from "react";
import type {
  MapPointInfo,
  MetricId,
  PointKind,
  PointResult,
} from "../api/planner.ts";
import { KIND_SHORT, pointTitle } from "../lib/points.ts";
import ScoreChip from "./ScoreChip.tsx";

// Infinity = "All"; it round-trips through localStorage and <option value> as "Infinity".
const TOP_OPTIONS = [25, 50, 100, Infinity] as const;
const TOP_KEY = "cc.worstTop";

function readTop(): number {
  try {
    const v = Number(localStorage.getItem(TOP_KEY));
    return (TOP_OPTIONS as readonly number[]).includes(v) ? v : TOP_OPTIONS[0];
  } catch {
    return TOP_OPTIONS[0];
  }
}

type Props = {
  metric: MetricId;
  /** Ids of the points to fix, worst first, already narrowed by the "Where to look" filter (see rankWorst). */
  ranked: readonly string[];
  pointsById: Map<string, MapPointInfo>;
  resultsById: Map<string, PointResult>;
  /** Point kinds picked in "Where to look"; only used to explain an empty list. */
  kinds: ReadonlySet<PointKind>;
  selectedId?: string;
  onSelect: (id: string) => void;
  onHover: (id?: string) => void;
};

export default function WorstList({
  metric,
  ranked,
  pointsById,
  resultsById,
  kinds,
  selectedId,
  onSelect,
  onHover,
}: Props) {
  const [limit, setLimit] = useState(readTop);
  const worst = ranked.slice(0, limit);
  const top = worst.length ? (resultsById.get(worst[0])?.priority ?? 0) : 0;

  function changeLimit(n: number) {
    setLimit(n);
    try {
      localStorage.setItem(TOP_KEY, String(n));
    } catch {
      /* per-viewer convenience only */
    }
  }
  return (
    <section aria-labelledby="worst-h" className="space-y-2.5">
      <div className="space-y-1.5">
        <h2
          id="worst-h"
          className="flex items-center gap-2 whitespace-nowrap text-xs font-semibold uppercase tracking-wide text-muted"
        >
          <span className="grid size-5 shrink-0 place-items-center rounded-full bg-primary text-[11px] text-primary-foreground">
            4
          </span>
          <span className="truncate">Worst points</span>
        </h2>
        <div className="flex items-center justify-between gap-3 pl-7">
          <p className="text-xs text-muted">
            <span className="font-semibold tabular-nums text-foreground">
              {ranked.length}
            </span>{" "}
            {ranked.length === 1 ? "point" : "points"} to fix
          </p>
          {ranked.length > 0 && (
            <select
              aria-label="How many worst points to list"
              value={limit}
              onChange={(e) => changeLimit(Number(e.target.value))}
              className="rounded-md border border-border bg-surface px-1.5 py-0.5 text-[11px] font-medium text-foreground focus-visible:outline-2 focus-visible:outline-primary"
            >
              {TOP_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n === Infinity ? "Show all" : `Show top ${n}`}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>
      {worst.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border-strong p-3 text-sm text-muted">
          {kinds.size === 0
            ? "Pick at least one point type above to list worst points."
            : "Nothing left to improve for this metric on the selected point types."}
        </p>
      ) : (
        <ol className="space-y-1">
          {worst.map((id, i) => {
            const p = pointsById.get(id);
            const r = resultsById.get(id);
            if (!p || !r) return null;
            const active = id === selectedId;
            return (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => onSelect(id)}
                  onMouseEnter={() => onHover(id)}
                  onMouseLeave={() => onHover(undefined)}
                  onFocus={() => onHover(id)}
                  onBlur={() => onHover(undefined)}
                  aria-current={active ? "true" : undefined}
                  className={`group grid w-full grid-cols-[1.5rem_1fr_auto] items-center gap-2 rounded-lg border px-2 py-1.5 text-left transition-colors ${
                    active
                      ? "border-primary bg-primary-soft"
                      : "border-transparent hover:border-border hover:bg-surface-2"
                  }`}
                >
                  <span
                    className={`grid size-6 place-items-center rounded-md text-xs font-semibold ${
                      i === 0
                        ? "bg-score-5 text-white"
                        : "bg-background text-muted"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {pointTitle(p)}
                    </span>
                    <span className="block truncate text-[11px] text-muted">
                      {KIND_SHORT[p.kind]}
                    </span>
                    <span
                      className="mt-1 block h-1 overflow-hidden rounded-full bg-border"
                      aria-hidden
                    >
                      <span
                        className="block h-full rounded-full bg-score-3"
                        style={{
                          width: `${top > 0 ? (r.priority / top) * 100 : 0}%`,
                        }}
                      />
                    </span>
                  </span>
                  <ScoreChip score={r.scores[metric]} />
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
