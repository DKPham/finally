import type { ConnectionStatus } from "@/lib/types";
import { fmtMoney, fmtSignedMoney, signClass } from "@/lib/format";

interface HeaderProps {
  totalValue: number | null;
  cashBalance: number | null;
  unrealizedPnl: number | null;
  status: ConnectionStatus;
}

const STATUS_META: Record<ConnectionStatus, { color: string; label: string }> = {
  connected: { color: "bg-up shadow-[0_0_8px_rgba(34,197,94,0.8)]", label: "LIVE" },
  reconnecting: { color: "bg-accent shadow-[0_0_8px_rgba(236,173,10,0.8)] dot-pulse", label: "RECONNECTING" },
  disconnected: { color: "bg-down shadow-[0_0_8px_rgba(239,68,68,0.8)]", label: "DISCONNECTED" },
};

function Stat({ label, children, testId }: { label: string; children: React.ReactNode; testId?: string }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-2xs uppercase tracking-[0.18em] text-mute-500">{label}</span>
      <span data-testid={testId} className="font-mono text-sm font-semibold tabular-nums text-slate-100">
        {children}
      </span>
    </div>
  );
}

export default function Header({ totalValue, cashBalance, unrealizedPnl, status }: HeaderProps) {
  const meta = STATUS_META[status];
  return (
    <header className="flex h-12 shrink-0 items-center justify-between gap-4 border-b border-ink-700 bg-ink-950/80 px-4">
      <div className="flex items-center gap-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-sm bg-accent font-mono text-sm font-black text-ink-950">
          F
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-base font-bold tracking-tight text-slate-100">
            Fin<span className="text-accent">Ally</span>
          </span>
          <span className="hidden font-mono text-2xs uppercase tracking-[0.2em] text-mute-500 sm:inline">
            AI Trading Workstation
          </span>
        </div>
      </div>

      <div className="flex items-center gap-5 sm:gap-7">
        <Stat label="Portfolio" testId="total-value">
          <span className="text-accent">{fmtMoney(totalValue)}</span>
        </Stat>
        <Stat label="Unrealized P&L" testId="unrealized-pnl">
          <span className={signClass(unrealizedPnl)}>{fmtSignedMoney(unrealizedPnl)}</span>
        </Stat>
        <Stat label="Cash" testId="cash-balance">
          {fmtMoney(cashBalance)}
        </Stat>
        <div
          data-testid="connection-status"
          data-status={status}
          title={`Price stream: ${status}`}
          className="flex items-center gap-2 border-l border-ink-700 pl-4"
        >
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${meta.color}`} aria-hidden />
          <span className="hidden font-mono text-2xs tracking-[0.15em] text-mute-400 md:inline">{meta.label}</span>
        </div>
      </div>
    </header>
  );
}
