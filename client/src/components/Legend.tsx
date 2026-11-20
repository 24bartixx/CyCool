import { Droplet, ListTree, X } from "lucide-react";
import { useState } from "react";
import type { MetricId } from "../api/planner.ts";
import { dec2 } from "../lib/format.ts";
import { METRIC_SHORT } from "../lib/icons.tsx";
import { SCORE_CLASSES, classRange, cssVar, useScoreScale } from "../lib/scale.ts";

type Props = {
  metric: MetricId;
  /** Some point kinds are left out of "Where to look", so the map greys them out. */
  filtered?: boolean;
};

const HIDDEN_KEY = "cc.legendHidden";

function readHidden(): boolean {
  try {
    return localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

export default function Legend({ metric, filtered = false }: Props) {
  const { breaks } = useScoreScale(metric);
  const [hidden, setHidden] = useState(readHidden);

  function changeHidden(next: boolean) {
    setHidden(next);
    try {
      localStorage.setItem(HIDDEN_KEY, next ? "1" : "0");
    } catch {
      /* per-viewer convenience only */
    }
  }

  if (hidden) {
    return (
      <button
        type="button"
        data-map-overlay
        onClick={() => changeHidden(false)}
        className="absolute bottom-6 left-3 z-[1000] hidden items-center gap-1.5 rounded-lg border border-border bg-surface/95 px-2.5 py-1.5 text-[11px] font-semibold text-foreground shadow-sm backdrop-blur hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-primary md:inline-flex"
      >
        <ListTree className="size-3.5" aria-hidden /> Show legend
      </button>
    );
  }

  return (
    <div
      data-map-overlay
      className="absolute bottom-6 left-3 z-[1000] hidden w-52 md:block rounded-xl border border-border bg-surface/95 p-3 text-[11px] shadow-sm backdrop-blur"
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <p className="font-semibold text-foreground">
          {METRIC_SHORT[metric]} score
        </p>
        <button
          type="button"
          onClick={() => changeHidden(true)}
          aria-label="Hide legend"
          title="Hide legend"
          className="-mr-1 grid size-5 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-foreground focus-visible:outline-2 focus-visible:outline-primary"
        >
          <X className="size-3.5" aria-hidden />
        </button>
      </div>
      <ul className="space-y-0.5">
        {SCORE_CLASSES.map((c, i) => (
          <li key={c.key} className="flex items-center gap-2">
            <span
              className="h-1.5 w-5 rounded-full"
              style={{ background: cssVar(c.token) }}
              aria-hidden
            />
            <span className="w-16 text-foreground">{c.label}</span>
            <span className="tabular-nums text-muted">
              {i === 0 ? `< ${dec2(classRange(0, breaks)[1])}` : classRange(i, breaks).map(dec2).join("–")}
            </span>
          </li>
        ))}
      </ul>
      <ul className="mt-2 space-y-1 border-t border-border pt-2 text-muted">
        <li className="flex items-center gap-2">
          <span
            className="grid size-3 place-items-center rounded-full border border-white bg-water text-white shadow"
            aria-hidden
          >
            <Droplet className="size-2" strokeWidth={3} />
          </span>{" "}
          Drinking fountain
        </li>
        <li className="flex items-center gap-2">
          <span
            className="h-2.5 w-3 rounded-[2px] border border-park bg-park/25"
            aria-hidden
          />{" "}
          Park
        </li>
        <li className="flex items-center gap-2">
          <span className="h-2.5 w-3 rounded-[2px] bg-park/30" aria-hidden />{" "}
          Short detour to shade
        </li>
        <li className="flex items-center gap-2">
          <span
            className="grid size-3 place-items-center rounded-[3px] border border-white bg-bike-parking text-[8px] font-bold leading-none text-white shadow"
            aria-hidden
          >
            P
          </span>{" "}
          Bicibox bike parking
        </li>
        <li className="flex items-center gap-2">
          <span
            className="size-3 rounded-full border-2 border-white bg-border-strong shadow"
            aria-hidden
          />{" "}
          Junction
        </li>
        <li className="flex items-center gap-2">
          <span
            className="size-3 rounded-[3px] border-2 border-white bg-border-strong shadow"
            aria-hidden
          />{" "}
          Bike station
        </li>
        <li className="flex items-center gap-2">
          <span
            className="size-3 rounded-full border-2 border-score-5"
            aria-hidden
          />{" "}
          Current worst point
        </li>
        {filtered && (
          <li className="flex items-center gap-2">
            <span className="h-1 w-3 rounded-full bg-network" aria-hidden /> Not
            in “Where to look”
          </li>
        )}
      </ul>
    </div>
  );
}
