import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { ApiError } from "../api/client.ts";
import {
  getMapData,
  postAutoPlan,
  postEvaluate,
  postRecommend,
  type AcceptedFix,
  type Evaluation,
  type MapData,
  type MetricId,
  type Recommendation,
} from "../api/planner.ts";

const METRICS: MetricId[] = ["water", "sun", "heat", "combined"];
export const DEFAULT_BUDGET = 50_000;
export const MAX_BUDGET = 10_000_000;
const STORAGE_KEY = "coolcycle.accepted.v1";

type Load<T> = { data?: T; error?: string; loading: boolean };

function readStoredPlan(): AcceptedFix[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (x): x is AcceptedFix =>
        typeof x === "object" &&
        x !== null &&
        typeof x.fix_id === "string" &&
        typeof x.point_id === "string",
    );
  } catch {
    return [];
  }
}

function storePlan(plan: AcceptedFix[]) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(plan));
  } catch {
    /* storage unavailable: the plan simply isn't remembered */
  }
}

const message = (e: unknown) =>
  e instanceof Error ? e.message : "Unexpected error";
const isAbort = (e: unknown) =>
  e instanceof DOMException && e.name === "AbortError";

export function usePlanner() {
  const [params, setParams] = useSearchParams();
  const metricParam = params.get("metric") as MetricId | null;
  const metric: MetricId =
    metricParam && METRICS.includes(metricParam) ? metricParam : "combined";
  const budgetParam = Number(params.get("budget"));
  const budget =
    Number.isFinite(budgetParam) && budgetParam > 0
      ? Math.min(budgetParam, MAX_BUDGET)
      : DEFAULT_BUDGET;

  const [mapData, setMapData] = useState<Load<MapData>>({ loading: true });
  const [mapReload, setMapReload] = useState(0);
  const [accepted, setAccepted] = useState<AcceptedFix[]>(readStoredPlan);
  const [evaluation, setEvaluation] = useState<Evaluation>();
  const [evalError, setEvalError] = useState<string>();
  const [evaluating, setEvaluating] = useState(false);
  const [notice, setNotice] = useState<string>();
  const [selectedId, setSelectedId] = useState<string>();
  const [recommendation, setRecommendation] = useState<Load<Recommendation>>({
    loading: false,
  });
  const [autoPlanning, setAutoPlanning] = useState(false);
  const lastGood = useRef<AcceptedFix[]>([]);

  // ---- static map data (once, with retry) ----
  useEffect(() => {
    const ctrl = new AbortController();
    setMapData({ loading: true });
    getMapData(ctrl.signal)
      .then((data) => setMapData({ data, loading: false }))
      .catch(
        (e) => !isAbort(e) && setMapData({ error: message(e), loading: false }),
      );
    return () => ctrl.abort();
  }, [mapReload]);

  // ---- evaluation: recomputed from scratch whenever metric, budget or the plan changes ----
  useEffect(() => {
    if (!mapData.data) return;
    const ctrl = new AbortController();
    setEvaluating(true);
    postEvaluate({ metric, budget, accepted }, ctrl.signal)
      .then((ev) => {
        setEvaluation(ev);
        setEvalError(undefined);
        lastGood.current = accepted;
        storePlan(accepted);
        setEvaluating(false);
      })
      .catch((e) => {
        if (isAbort(e)) return;
        setEvaluating(false);
        if (
          e instanceof ApiError &&
          e.status === 422 &&
          accepted !== lastGood.current
        ) {
          // The server rejected the change (e.g. over budget): roll back to the last valid plan.
          setNotice(e.message);
          setAccepted(lastGood.current);
          return;
        }
        setEvalError(message(e));
      });
    return () => ctrl.abort();
  }, [mapData.data, metric, budget, accepted]);

  // ---- recommendations for the selected point, consistent with the evaluation on screen ----
  useEffect(() => {
    if (!selectedId || !evaluation) {
      setRecommendation({ loading: false });
      return;
    }
    const ctrl = new AbortController();
    setRecommendation((r) => ({ ...r, loading: true, error: undefined }));
    postRecommend(
      {
        metric: evaluation.metric,
        budget: evaluation.budget.total,
        accepted: evaluation.plan.map(({ fix_id, point_id }) => ({
          fix_id,
          point_id,
        })),
        point_id: selectedId,
      },
      ctrl.signal,
    )
      .then((data) => setRecommendation({ data, loading: false }))
      .catch(
        (e) =>
          !isAbort(e) &&
          setRecommendation({ error: message(e), loading: false }),
      );
    return () => ctrl.abort();
  }, [selectedId, evaluation]);

  const setMetric = useCallback(
    (m: MetricId) =>
      setParams(
        (p) => {
          p.set("metric", m);
          return p;
        },
        { replace: true },
      ),
    [setParams],
  );

  const setBudget = useCallback(
    (b: number) =>
      setParams(
        (p) => {
          p.set("budget", String(Math.round(b)));
          return p;
        },
        { replace: true },
      ),
    [setParams],
  );

  const accept = useCallback((fix_id: string, point_id: string) => {
    setNotice(undefined);
    setAccepted((prev) => [...prev, { fix_id, point_id }]);
  }, []);
  const remove = useCallback((fixId: string, pointId: string) => {
    setNotice(undefined);
    setAccepted((prev) =>
      prev.filter((fix) => fix.fix_id !== fixId || fix.point_id !== pointId),
    );
  }, []);
  const undo = useCallback(() => {
    setNotice(undefined);
    setAccepted((prev) => prev.slice(0, -1));
  }, []);
  const reset = useCallback(() => {
    setNotice(undefined);
    setAccepted([]);
  }, []);

  /** Lets the server fill the rest of the budget with the best fixes per euro for the current metric. */
  const autoPlan = useCallback(() => {
    if (!evaluation) return;
    setNotice(undefined);
    setAutoPlanning(true);
    const current = evaluation.plan.map(({ fix_id, point_id }) => ({
      fix_id,
      point_id,
    }));
    postAutoPlan({
      metric: evaluation.metric,
      budget: evaluation.budget.total,
      accepted: current,
    })
      .then((res) => {
        if (res.added.length === 0)
          setNotice("No affordable fix improves this metric any further.");
        else setAccepted(res.accepted);
      })
      .catch((e) => setNotice(`Couldn't fill the budget: ${message(e)}`))
      .finally(() => setAutoPlanning(false));
  }, [evaluation]);

  const pointsById = useMemo(
    () => new Map(mapData.data?.points.map((p) => [p.id, p])),
    [mapData.data],
  );
  const trailsById = useMemo(
    () => new Map(mapData.data?.trails.map((t) => [t.id, t])),
    [mapData.data],
  );
  const resultsById = useMemo(
    () => new Map(evaluation?.points.map((p) => [p.id, p])),
    [evaluation],
  );

  return {
    metric,
    budget,
    setMetric,
    setBudget,
    mapData,
    retryMapData: () => setMapReload((n) => n + 1),
    evaluation,
    evalError,
    evaluating,
    notice,
    dismissNotice: () => setNotice(undefined),
    accepted,
    accept,
    remove,
    undo,
    reset,
    autoPlan,
    autoPlanning,
    selectedId,
    setSelectedId,
    recommendation,
    pointsById,
    trailsById,
    resultsById,
  };
}
