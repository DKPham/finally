"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Header from "./Header";
import Watchlist from "./Watchlist";
import MainChart from "./MainChart";
import Heatmap from "./Heatmap";
import PnlChart from "./PnlChart";
import PositionsTable from "./PositionsTable";
import TradeBar from "./TradeBar";
import ChatPanel from "./ChatPanel";
import { api } from "@/lib/api";
import { PriceStore } from "@/lib/priceStore";
import { usePriceSnapshot, usePriceStream } from "@/lib/usePriceStream";
import { computeLivePortfolio } from "@/lib/portfolio";
import type { ChatMessage, Portfolio, Side, Snapshot, WatchlistItem } from "@/lib/types";

export const HISTORY_REFRESH_MS = 30_000;

let tempId = 0;
const localId = () => `local-${Date.now()}-${++tempId}`;

export default function Workstation({ store: injected }: { store?: PriceStore } = {}) {
  const storeRef = useRef<PriceStore>(injected ?? new PriceStore());
  const store = storeRef.current;
  const status = usePriceStream(store);
  const { latest, history } = usePriceSnapshot(store);

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatLoadError, setChatLoadError] = useState<string | null>(null);

  const refreshPortfolio = useCallback(async () => {
    try {
      setPortfolio(await api.getPortfolio());
    } catch (e) {
      console.error("portfolio fetch failed", e);
    }
  }, []);
  const refreshWatchlist = useCallback(async () => {
    try {
      setWatchlist(await api.getWatchlist());
    } catch (e) {
      console.error("watchlist fetch failed", e);
    }
  }, []);
  const refreshHistory = useCallback(async () => {
    try {
      setSnapshots(await api.getHistory());
    } catch (e) {
      console.error("history fetch failed", e);
    }
  }, []);

  // Initial loads + P&L history refresh every 30s.
  useEffect(() => {
    void refreshPortfolio();
    void refreshWatchlist();
    void refreshHistory();
    api
      .getChatHistory()
      .then(setMessages)
      .catch(() => setChatLoadError("Couldn't load chat history."));
    const id = setInterval(() => void refreshHistory(), HISTORY_REFRESH_MS);
    return () => clearInterval(id);
  }, [refreshPortfolio, refreshWatchlist, refreshHistory]);

  // Selection defaults to the first watchlist ticker.
  const activeTicker = selected ?? watchlist[0]?.ticker ?? null;

  const live = useMemo(() => computeLivePortfolio(portfolio, latest), [portfolio, latest]);

  const handleTrade = useCallback(
    async (ticker: string, quantity: number, side: Side) => {
      const res = await api.trade(ticker, quantity, side);
      setPortfolio(res.portfolio);
      void refreshHistory();
      void refreshWatchlist(); // trading an unwatched ticker auto-adds it
      return res.trade;
    },
    [refreshHistory, refreshWatchlist],
  );

  const handleAdd = useCallback(
    async (ticker: string) => {
      await api.addWatchlist(ticker);
      await refreshWatchlist();
      void refreshPortfolio();
    },
    [refreshWatchlist, refreshPortfolio],
  );

  const handleRemove = useCallback(
    async (ticker: string) => {
      await api.removeWatchlist(ticker);
      setWatchlist((w) => w.filter((i) => i.ticker !== ticker));
      setSelected((s) => (s === ticker ? null : s));
      await refreshWatchlist();
      void refreshPortfolio();
    },
    [refreshWatchlist, refreshPortfolio],
  );

  const handleSend = useCallback(
    async (text: string) => {
      const userMsg: ChatMessage = {
        id: localId(),
        role: "user",
        content: text,
        actions: null,
        created_at: new Date().toISOString(),
      };
      setMessages((m) => [...m, userMsg]);
      setChatLoading(true);
      try {
        const res = await api.chat(text);
        setMessages((m) => [
          ...m,
          {
            id: localId(),
            role: "assistant",
            content: res.message,
            actions: res.actions ?? [],
            created_at: new Date().toISOString(),
          },
        ]);
        if (res.actions && res.actions.length > 0) {
          void refreshPortfolio();
          void refreshWatchlist();
          void refreshHistory();
        }
      } catch (e) {
        setMessages((m) => [
          ...m,
          {
            id: localId(),
            role: "assistant",
            content: `Sorry, I couldn't reach the server — ${e instanceof Error ? e.message : "please try again."}`,
            actions: [],
            created_at: new Date().toISOString(),
          },
        ]);
      } finally {
        setChatLoading(false);
      }
    },
    [refreshPortfolio, refreshWatchlist, refreshHistory],
  );

  const priceFor = useCallback(
    (t: string) => latest[t]?.price ?? watchlist.find((w) => w.ticker === t)?.price ?? undefined,
    [latest, watchlist],
  );

  const positions = live?.positions ?? [];

  return (
    <div className="terminal-bg flex h-screen flex-col overflow-hidden bg-ink-900 text-slate-200 max-lg:h-auto max-lg:min-h-screen max-lg:overflow-visible">
      <Header
        totalValue={live?.total_value ?? null}
        cashBalance={live?.cash_balance ?? null}
        unrealizedPnl={live?.unrealized_pnl ?? null}
        status={status}
      />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main className="grid min-h-0 min-w-0 flex-1 gap-1 p-1 max-lg:grid-cols-1 lg:grid-cols-[minmax(300px,340px)_1fr]">
          <Watchlist
            items={watchlist}
            latest={latest}
            history={history}
            selected={activeTicker}
            onSelect={setSelected}
            onAdd={handleAdd}
            onRemove={handleRemove}
          />
          <div className="flex min-h-0 min-w-0 flex-col gap-1">
            <div className="flex min-h-[220px] flex-[1.25] flex-col">
              <MainChart
                ticker={activeTicker}
                points={activeTicker ? history[activeTicker] : undefined}
                latest={activeTicker ? latest[activeTicker] : undefined}
              />
            </div>
            <TradeBar
              selectedTicker={activeTicker}
              priceFor={priceFor}
              cash={live?.cash_balance ?? null}
              onTrade={handleTrade}
            />
            <div className="grid min-h-[200px] flex-1 grid-cols-1 gap-1 md:grid-cols-2">
              <Heatmap positions={positions} onSelect={setSelected} />
              <PnlChart history={snapshots} />
            </div>
            <div className="flex min-h-[150px] flex-[0.85] flex-col">
              <PositionsTable positions={positions} onSelect={setSelected} />
            </div>
          </div>
        </main>
        <ChatPanel
          open={chatOpen}
          onToggle={() => setChatOpen((o) => !o)}
          messages={messages}
          loading={chatLoading}
          onSend={(t) => void handleSend(t)}
          loadError={chatLoadError}
        />
      </div>
    </div>
  );
}
