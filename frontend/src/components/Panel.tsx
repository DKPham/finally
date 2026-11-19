import type { ReactNode } from "react";

interface PanelProps {
  title: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  testId?: string;
  /** Extra data-* attributes for the root element (e.g. {"data-ticker": "AAPL"}). */
  dataAttrs?: Record<`data-${string}`, string | undefined>;
}

export default function Panel({ title, right, children, className = "", bodyClassName = "", testId, dataAttrs }: PanelProps) {
  return (
    <section
      data-testid={testId}
      {...dataAttrs}
      className={`flex min-h-0 min-w-0 flex-1 flex-col border border-ink-700 bg-ink-850/80 ${className}`}
    >
      <header className="flex h-7 shrink-0 items-center justify-between gap-2 border-b border-ink-700 bg-ink-800/70 px-2.5">
        <h2 className="flex items-center gap-2 text-2xs font-semibold uppercase tracking-[0.18em] text-mute-400">
          <span className="h-2.5 w-0.5 bg-accent" aria-hidden />
          {title}
        </h2>
        {right ? <div className="flex items-center gap-2 text-2xs text-mute-500">{right}</div> : null}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}

export function EmptyState({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <div
      data-testid={testId}
      className="flex h-full min-h-[80px] items-center justify-center px-4 text-center font-mono text-xs text-mute-500"
    >
      {children}
    </div>
  );
}
