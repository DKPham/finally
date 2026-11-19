"use client";

import { useEffect, useState, type FormEvent } from "react";
import type { Side, Trade } from "@/lib/types";
import { fmtMoney, fmtPrice, fmtQty } from "@/lib/format";

const TICKER_RE = /^[A-Z][A-Z.]{0,5}$/;

interface TradeBarProps {
  /** Pre-fills the ticker field when the selection changes. */
  selectedTicker: string | null;
  /** Latest streamed price for the ticker currently typed, used for the order estimate. */
  priceFor: (ticker: string) => number | undefined;
  cash: number | null;
  onTrade: (ticker: string, quantity: number, side: Side) => Promise<Trade>;
}

export default function TradeBar({ selectedTicker, priceFor, cash, onTrade }: TradeBarProps) {
  const [ticker, setTicker] = useState(selectedTicker ?? "");
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState<Side | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (selectedTicker) setTicker(selectedTicker);
  }, [selectedTicker]);

  const run = async (side: Side) => {
    setError(null);
    setSuccess(null);
    const t = ticker.trim().toUpperCase();
    const q = Number(qty);
    if (!TICKER_RE.test(t)) {
      setError("Enter a valid ticker");
      return;
    }
    if (!qty.trim() || !Number.isFinite(q) || q <= 0) {
      setError("Quantity must be greater than 0");
      return;
    }
    setBusy(side);
    try {
      const trade = await onTrade(t, q, side);
      setSuccess(
        `${trade.side === "buy" ? "Bought" : "Sold"} ${fmtQty(trade.quantity)} ${trade.ticker} @ $${fmtPrice(trade.price)}`,
      );
      setQty("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  // Enter never places an order implicitly; the user must click Buy or Sell.
  const onSubmit = (e: FormEvent) => e.preventDefault();

  const px = ticker ? priceFor(ticker.trim().toUpperCase()) : undefined;
  const q = Number(qty);
  const estimate = px != null && Number.isFinite(q) && q > 0 ? px * q : null;

  return (
    <form
      onSubmit={onSubmit}
      data-testid="trade-bar"
      className="flex shrink-0 flex-wrap items-center gap-2 border border-ink-700 bg-ink-850/80 px-2.5 py-1.5"
    >
      <span className="flex items-center gap-2 text-2xs font-semibold uppercase tracking-[0.18em] text-mute-400">
        <span className="h-2.5 w-0.5 bg-accent" aria-hidden />
        Order
      </span>
      <input
        data-testid="trade-ticker"
        aria-label="Trade ticker"
        value={ticker}
        onChange={(e) => setTicker(e.target.value.toUpperCase())}
        placeholder="TICKER"
        maxLength={6}
        className="w-20 rounded-sm border border-ink-600 bg-ink-900 px-2 py-1 font-mono text-xs uppercase text-slate-100 placeholder:text-mute-600 focus:border-primary focus:outline-none"
      />
      <input
        data-testid="trade-quantity"
        aria-label="Trade quantity"
        value={qty}
        onChange={(e) => setQty(e.target.value)}
        placeholder="QTY"
        inputMode="decimal"
        type="number"
        min="0"
        step="any"
        className="w-24 rounded-sm border border-ink-600 bg-ink-900 px-2 py-1 font-mono text-xs text-slate-100 placeholder:text-mute-600 focus:border-primary focus:outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
      />
      <button
        type="button"
        data-testid="trade-buy"
        disabled={busy !== null}
        onClick={() => void run("buy")}
        className="rounded-sm border border-up/60 bg-up/15 px-4 py-1 text-xs font-bold uppercase tracking-wider text-up transition hover:bg-up/25 disabled:opacity-40"
      >
        {busy === "buy" ? "…" : "Buy"}
      </button>
      <button
        type="button"
        data-testid="trade-sell"
        disabled={busy !== null}
        onClick={() => void run("sell")}
        className="rounded-sm border border-down/60 bg-down/15 px-4 py-1 text-xs font-bold uppercase tracking-wider text-down transition hover:bg-down/25 disabled:opacity-40"
      >
        {busy === "sell" ? "…" : "Sell"}
      </button>
      <span className="hidden font-mono text-2xs text-mute-500 md:inline">
        {estimate != null ? `≈ ${fmtMoney(estimate)}` : "MKT · instant fill"}
        {cash != null ? ` · cash ${fmtMoney(cash)}` : ""}
      </span>
      <span className="ml-auto min-w-0 truncate font-mono text-2xs" aria-live="polite">
        {error ? (
          <span data-testid="trade-error" role="alert" className="text-down">
            ✗ {error}
          </span>
        ) : success ? (
          <span data-testid="trade-success" className="text-up">
            ✓ {success}
          </span>
        ) : null}
      </span>
    </form>
  );
}
