import { FileDown, LoaderCircle } from "lucide-react";
import Wordmark from "./Wordmark.tsx";

type Props = {
  onExport: () => void;
  /** Why the plan can't be exported right now (no fix yet, still loading); undefined when it can. */
  exportBlockedReason?: string;
  exporting: boolean;
  exportFailed: boolean;
};

export default function AppHeader({
  onExport,
  exportBlockedReason,
  exporting,
  exportFailed,
}: Props) {
  return (
    <header className="z-[1100] flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface px-4">
      <div className="mr-auto min-w-0">
        <Wordmark className="h-9 w-auto" />
      </div>
      {exportFailed && (
        <span role="alert" className="hidden text-xs text-danger md:inline">
          Couldn't create the PDF. Try again.
        </span>
      )}
      <button
        type="button"
        onClick={onExport}
        disabled={!!exportBlockedReason || exporting}
        title={
          exportBlockedReason ??
          "Download the plan as a PDF: what it changes and where each fix goes"
        }
        aria-label={
          exportFailed
            ? "Export PDF. The last export failed, try again"
            : undefined
        }
        className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-medium text-foreground transition-colors enabled:hover:bg-surface-2 disabled:opacity-50"
      >
        {exporting ? (
          <LoaderCircle
            className="size-4 animate-spin text-primary"
            aria-hidden
          />
        ) : (
          <FileDown className="size-4 text-primary" aria-hidden />
        )}
        <span className="hidden sm:inline">
          {exporting ? "Preparing PDF…" : "Export PDF"}
        </span>
        <span className="sm:hidden">PDF</span>
      </button>
    </header>
  );
}
