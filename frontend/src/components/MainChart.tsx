"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import Panel, { EmptyState } from "./Panel";
import type { PricePoint, PriceUpdate } from "@/lib/types";
import { fmtPct, fmtPrice, fmtTime, signClass } from "@/lib/format";

interface MainChartProps {
  ticker: string | null;
  points: PricePoint[] | undefined;
  latest: PriceUpdate | undefined;
}

export default function MainChart({ ticker, points, latest }: MainChartProps) {
  const data = points ?? [];
  const first = data[0]?.price;
  const last = data[data.length - 1]?.price;
  const up = first == null || last == null || last >= first;
  const stroke = up ? "#22c55e" : "#ef4444";
  const chg = latest?.session_change_percent;

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          Chart
          <span data-testid="main-chart-ticker" className="font-mono text-xs tracking-normal text-accent">
            {ticker ?? "—"}
          </span>
        </span>
      }
      right={
        latest ? (
          <span className="flex items-center gap-3 font-mono text-xs">
            <span data-testid="main-chart-price" className="text-slate-100">
              {fmtPrice(latest.price)}
            </span>
            <span className={signClass(chg)}>{fmtPct(chg)}</span>
            <span className="hidden text-mute-500 sm:inline">since open</span>
          </span>
        ) : null
      }
      testId="main-chart"
      dataAttrs={{ "data-ticker": ticker ?? undefined }}
      bodyClassName="p-1"
    >
      {!ticker ? (
        <EmptyState>Select a ticker from the watchlist.</EmptyState>
      ) : data.length < 2 ? (
        <EmptyState>Waiting for {ticker} prices…</EmptyState>
      ) : (
        <ResponsiveContainer width="100%" height="100%" minHeight={120}>
          <AreaChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="mainFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={stroke} stopOpacity={0.28} />
                <stop offset="100%" stopColor={stroke} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1f2632" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={fmtTime}
              stroke="#4f586a"
              tick={{ fontSize: 10, fontFamily: "ui-monospace, monospace" }}
              minTickGap={60}
            />
            <YAxis
              orientation="right"
              domain={["auto", "auto"]}
              tickFormatter={(v: number) => fmtPrice(v)}
              stroke="#4f586a"
              tick={{ fontSize: 10, fontFamily: "ui-monospace, monospace" }}
              width={64}
            />
            <Tooltip
              isAnimationActive={false}
              contentStyle={{
                background: "#11161e",
                border: "1px solid #2a3240",
                fontFamily: "ui-monospace, monospace",
                fontSize: 11,
              }}
              labelFormatter={(v) => fmtTime(Number(v))}
              formatter={(v) => [fmtPrice(Number(v)), ticker]}
            />
            <Area
              type="linear"
              dataKey="price"
              stroke={stroke}
              strokeWidth={1.5}
              fill="url(#mainFill)"
              dot={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </Panel>
  );
}
