import Panel, { EmptyState } from "./Panel";
import type { Position } from "@/lib/types";
import { fmtMoney, fmtPct, fmtPrice, fmtQty, fmtSignedMoney, signClass } from "@/lib/format";

interface PositionsTableProps {
  positions: Position[];
  onSelect?: (ticker: string) => void;
}

export default function PositionsTable({ positions, onSelect }: PositionsTableProps) {
  return (
    <Panel
      title="Positions"
      testId="positions-table"
      right={<span className="font-mono">{positions.length}</span>}
      bodyClassName="overflow-auto"
    >
      {positions.length === 0 ? (
        <EmptyState testId="positions-empty">No positions yet — buy something or ask FinAlly.</EmptyState>
      ) : (
        <table className="w-full border-collapse font-mono text-xs tabular-nums">
          <thead className="sticky top-0 bg-ink-850 text-2xs uppercase tracking-wider text-mute-500">
            <tr className="border-b border-ink-700">
              <th className="px-2.5 py-1 text-left font-medium">Ticker</th>
              <th className="px-2 py-1 text-right font-medium">Qty</th>
              <th className="px-2 py-1 text-right font-medium">Avg Cost</th>
              <th className="px-2 py-1 text-right font-medium">Price</th>
              <th className="px-2 py-1 text-right font-medium">Mkt Value</th>
              <th className="px-2 py-1 text-right font-medium">Unrl P&L</th>
              <th className="px-2.5 py-1 text-right font-medium">% Chg</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr
                key={p.ticker}
                data-testid={`position-row-${p.ticker}`}
                onClick={() => onSelect?.(p.ticker)}
                className="cursor-pointer border-b border-ink-800 hover:bg-ink-800"
              >
                <td className="px-2.5 py-1 font-semibold text-slate-100">{p.ticker}</td>
                <td data-testid={`position-qty-${p.ticker}`} className="px-2 py-1 text-right text-slate-200">
                  {fmtQty(p.quantity)}
                </td>
                <td className="px-2 py-1 text-right text-mute-400">{fmtPrice(p.avg_cost)}</td>
                <td data-testid={`position-price-${p.ticker}`} className="px-2 py-1 text-right text-slate-200">
                  {fmtPrice(p.current_price)}
                </td>
                <td className="px-2 py-1 text-right text-slate-200">{fmtMoney(p.market_value)}</td>
                <td
                  data-testid={`position-pnl-${p.ticker}`}
                  className={`px-2 py-1 text-right ${signClass(p.unrealized_pnl)}`}
                >
                  {fmtSignedMoney(p.unrealized_pnl)}
                </td>
                <td className={`px-2.5 py-1 text-right ${signClass(p.unrealized_pnl_percent)}`}>
                  {fmtPct(p.unrealized_pnl_percent)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
