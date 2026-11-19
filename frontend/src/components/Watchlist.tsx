"use client";

import { useState, type FormEvent } from "react";
import Panel, { EmptyState } from "./Panel";
import PriceCell from "./PriceCell";
import Sparkline from "./Sparkline";
import type { PriceBatch, PricePoint, WatchlistItem } from "@/lib/types";
import { fmtPct, signClass } from "@/lib/format";

const TICKER_RE = /^[A-Z][A-Z.]{0,5}$/;

interface WatchlistProps {
  items: WatchlistItem[];
  latest: PriceBatch;
  history: Record<string, PricePoint[]>;
  selected: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<void>;
  onRemove: (ticker: string) => Promise<void>;
}

export default function Watchlist({ items, latest, history, selected, onSelect, onAdd, onRemove }: WatchlistProps) {
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ticker = input.trim().toUpperCase();
    if (!ticker) return;
    if (!TICKER_RE.test(ticker)) {
      setError(`"${ticker}" is not a valid ticker`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onAdd(ticker);
      setInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (ticker: string) => {
    setError(null);
    try {
      await onRemove(ticker);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Panel
      title="Watchlist"
      testId="watchlist"
      right={<span className="font-mono">{items.length}/30</span>}
      bodyClassName="flex flex-col"
    >
      <div className="grid shrink-0 grid-cols-[minmax(52px,1fr)_76px_72px_60px_18px] items-center gap-1.5 border-b border-ink-700 px-2.5 py-1 text-2xs uppercase tracking-wider text-mute-500">
        <span>Sym</span>
        <span>Trend</span>
        <span className="text-right">Last</span>
        <span className="text-right">Chg %</span>
        <span />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {items.length === 0 ? (
          <EmptyState testId="watchlist-empty">Watchlist is empty — add a ticker below.</EmptyState>
        ) : (
          items.map((item) => {
            const live = latest[item.ticker];
            const price = live?.price ?? item.price;
            const chg = live?.session_change_percent ?? item.session_change_percent;
            const isSel = selected === item.ticker;
            return (
              <div
                key={item.ticker}
                data-testid={`watchlist-row-${item.ticker}`}
                data-selected={isSel ? "true" : undefined}
                role="button"
                tabIndex={0}
                onClick={() => onSelect(item.ticker)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(item.ticker);
                  }
                }}
                className={`group grid cursor-pointer grid-cols-[minmax(52px,1fr)_76px_72px_60px_18px] items-center gap-1.5 border-b border-l-2 border-b-ink-800 px-2.5 py-1 text-xs transition-colors hover:bg-ink-800 ${
                  isSel ? "border-l-accent bg-ink-800/90" : "border-l-transparent"
                }`}
              >
                <span className={`font-mono font-semibold ${isSel ? "text-accent" : "text-slate-100"}`}>
                  {item.ticker}
                </span>
                <Sparkline points={history[item.ticker]} up={(chg ?? 0) >= 0} />
                <span className="text-right">
                  <PriceCell price={price} testId={`watchlist-price-${item.ticker}`} className="text-slate-100" />
                </span>
                <span
                  data-testid={`watchlist-change-${item.ticker}`}
                  className={`text-right font-mono tabular-nums ${signClass(chg)}`}
                >
                  {fmtPct(chg)}
                </span>
                <button
                  type="button"
                  data-testid={`watchlist-remove-${item.ticker}`}
                  aria-label={`Remove ${item.ticker} from watchlist`}
                  title={`Remove ${item.ticker}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    void remove(item.ticker);
                  }}
                  className="flex h-4 w-4 items-center justify-center rounded-sm text-mute-600 opacity-60 transition hover:bg-down/20 hover:text-down group-hover:opacity-100"
                >
                  ×
                </button>
              </div>
            );
          })
        )}
      </div>
      <form onSubmit={submit} className="shrink-0 border-t border-ink-700 p-2">
        <div className="flex gap-1.5">
          <input
            data-testid="watchlist-add-input"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            placeholder="ADD TICKER"
            maxLength={6}
            aria-label="Ticker to add"
            className="min-w-0 flex-1 rounded-sm border border-ink-600 bg-ink-900 px-2 py-1 font-mono text-xs uppercase text-slate-100 placeholder:text-mute-600 focus:border-primary focus:outline-none"
          />
          <button
            type="submit"
            data-testid="watchlist-add-button"
            disabled={busy || !input.trim()}
            className="rounded-sm bg-secondary px-3 py-1 text-xs font-semibold text-white transition hover:bg-secondary-bright disabled:cursor-not-allowed disabled:opacity-40"
          >
            Add
          </button>
        </div>
        {error ? (
          <p data-testid="watchlist-error" role="alert" className="mt-1.5 font-mono text-2xs text-down">
            {error}
          </p>
        ) : null}
      </form>
    </Panel>
  );
}
