import { MapPin, X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import type {
  MapPointInfo,
  MetricId,
  PointResult,
  Trail,
} from "../api/planner.ts";
import { celsius, int, metres } from "../lib/format.ts";
import { METRIC_ICON, METRIC_SHORT } from "../lib/icons.tsx";
import { KIND_LABEL, pointSubtitle, pointTitle } from "../lib/points.ts";
import { scoreColor } from "../lib/scale.ts";
import ScoreChip from "./ScoreChip.tsx";

const PLACEMENT = {
  /** Wide screens: inside the map popup above the point. MapView sets the height cap so it fits the map. */
  popup: "w-[360px] max-h-(--cc-popup-max-h)",
  /** Smaller screens: over the map, as a bottom sheet on phones and a right-hand panel on tablets. */
  overlay:
    "absolute inset-x-0 bottom-0 z-[1001] max-h-[70%] border-t shadow-2xl md:inset-x-auto md:right-0 md:top-0 md:max-h-none md:w-[400px] md:border-l md:border-t-0",
};

type Props = {
  placement: keyof typeof PLACEMENT;
  point: MapPointInfo;
  trail?: Trail;
  result?: PointResult;
  metric: MetricId;
  isWorst: boolean;
  onClose: () => void;
  /** The recommended fixes, when they are shown inside the details (smaller screens). */
  children?: ReactNode;
};

function MetricRow(props: {
  metric: MetricId;
  active: boolean;
  score: number;
  detail: string;
  dense: boolean;
}) {
  const { metric, active, score, detail, dense } = props;
  const Icon = METRIC_ICON[metric];
  return (
    <div
      className={`rounded-lg px-2.5 ${dense ? "py-1.5" : "py-2"} ${active ? "bg-primary-soft ring-1 ring-primary/30" : ""}`}
    >
      <div className="flex items-center gap-2">
        <Icon
          className={`size-4 ${active ? "text-primary" : "text-muted"}`}
          aria-hidden
        />
        <span className="text-sm font-medium">{METRIC_SHORT[metric]}</span>
        <span className="ml-auto">
          <ScoreChip score={score} showLabel />
        </span>
      </div>
      <div
        className={`h-1.5 overflow-hidden rounded-full bg-border ${dense ? "mt-1" : "mt-1.5"}`}
        aria-hidden
      >
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.max(2, score * 100)}%`,
            background: scoreColor(score),
          }}
        />
      </div>
      <p className={`text-xs text-muted ${dense ? "mt-0.5" : "mt-1"}`}>
        {detail}
      </p>
    </div>
  );
}

export default function PointDrawer(props: Props) {
  const {
    placement,
    point,
    trail,
    result,
    metric,
    isWorst,
    onClose,
    children,
  } = props;
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus({ preventScroll: true });
  }, [point.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const raw = result?.raw;
  // The popup sits on the map, so it is kept tighter than the full-height panel.
  const dense = placement === "popup";

  return (
    <aside
      aria-label={`Details for ${pointTitle(point)}`}
      className={`flex flex-col border-border bg-surface ${PLACEMENT[placement]}`}
    >
      <div
        className={`flex items-start gap-2 border-b border-border ${dense ? "px-3 py-2.5" : "p-4"}`}
      >
        <MapPin className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded-md bg-background px-1.5 py-0.5 text-[11px] font-medium text-muted">
              {KIND_LABEL[point.kind]}
              {point.kind === "segment" && (
                <span title="Length of this piece">
                  {" "}
                  · {metres(point.length_m)}
                </span>
              )}
            </span>
            {isWorst && (
              <span className="rounded-md bg-score-5 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                Worst for {METRIC_SHORT[metric]}
              </span>
            )}
          </div>
          <h2
            className={`mt-1 font-semibold leading-snug ${dense ? "text-base" : "text-lg"}`}
          >
            {pointTitle(point)}
          </h2>
          <p className="text-xs text-muted">{pointSubtitle(point, trail)}</p>
        </div>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          aria-label="Close details"
          className="rounded-md p-1 text-muted hover:bg-background hover:text-foreground"
        >
          <X className="size-5" />
        </button>
      </div>

      <div
        className={`flex-1 overflow-y-auto ${dense ? "space-y-3 p-2" : "space-y-5 p-4"}`}
      >
        {raw && result && (
          <section aria-label="Scores at this point" className="space-y-1">
            {(
              [
                {
                  id: "water",
                  detail: `${metres(raw.water_dist_m)} to the nearest drinking water`,
                },
                {
                  id: "sun",
                  detail:
                    `Solar index ${int(raw.solar)}` +
                    (raw.wait_s != null
                      ? ` · red light ${int(raw.wait_s)} s at ${int(raw.shade_pct)} % shade`
                      : ""),
                },
                {
                  id: "heat",
                  detail:
                    `UTCI ${celsius(raw.utci_c)} at 14:00` +
                    (raw.utci_c < raw.utci_base_c - 0.05
                      ? ` (was ${celsius(raw.utci_base_c)})`
                      : "") +
                    (point.utci_source === "computed"
                      ? ` on a hot afternoon · ${int(100 * (point.sun_share ?? 0))} % direct sun, ground ${celsius(point.ground_temp_c)} (from real weather and Landsat)`
                      : " · synthetic VAS-R1 value"),
                },
                { id: "combined", detail: "Mean of water, sun and heat" },
              ] satisfies { id: MetricId; detail: string }[]
            )
              // Worst first, so the planner reads the biggest problem at this point at the top.
              .sort((a, b) => result.scores[b.id] - result.scores[a.id])
              .map(({ id, detail }) => (
                <MetricRow
                  key={id}
                  metric={id}
                  active={metric === id}
                  score={result.scores[id]}
                  detail={detail}
                  dense={dense}
                />
              ))}
          </section>
        )}

        {children}
      </div>
    </aside>
  );
}
