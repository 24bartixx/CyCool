import { BookOpen } from 'lucide-react'

type Props = { onOpenAssumptions: () => void; assumptionsDisabled: boolean }

export default function AppHeader({ onOpenAssumptions, assumptionsDisabled }: Props) {
  return (
    <header className="z-[1100] flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface px-4">
      <img src="/favicon.svg" alt="" className="size-8" />
      <div className="min-w-0 leading-tight">
        <p className="font-semibold tracking-tight text-primary">CyCool</p>
        <p className="truncate text-xs text-muted">Heat-comfort planner for Viladecans cycle trails</p>
      </div>
      <button
        type="button"
        onClick={onOpenAssumptions}
        disabled={assumptionsDisabled}
        className="ml-auto inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-surface-2 disabled:opacity-50"
      >
        <BookOpen className="size-4 text-primary" aria-hidden />
        <span className="hidden sm:inline">Data & assumptions</span>
        <span className="sm:hidden">Data</span>
      </button>
    </header>
  )
}
