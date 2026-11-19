"use client";

import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import Panel, { EmptyState } from "./Panel";
import type { Snapshot } from "@/lib/types";
import { fmtMoney, fmtSignedMoney, signClass } from "@/lib/format";

interface PnlChartProps {
  history: Snapshot[];
}

const fmtClock = (ms: number) => new Date(ms).toLocaleTimeString("en-US", { hour12: false });

// Up to 2 decimals so a narrow value range doesn't produce duplicate tick labels.
const axisMoney = new Intl.NumberFormat("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

export default function PnlChart({ history }: PnlChartProps) {
  const data = history
    .map((s) => ({ t: Date.parse(s.recorded_at), v: s.total_value }))
    .filter((d) => Number.isFinite(d.t) && Number.isFinite(d.v));
  const base = data[0]?.v;
  const last = data[data.length - 1]?.v;
  const delta = base != null && last != null ? last - base : null;
  const up = (delta ?? 0) >= 0;
  const stroke = up ? "#22c55e" : "#ef4444";

  return (
    <Panel
      title="Portfolio Value"
      testId="pnl-chart"
      right={
        delta != null ? (
          <span className={`font-mono ${signClass(delta)}`}>{fmtSignedMoney(delta)}</span>
        ) : null
      }
      bodyClassName="p-1"
    >
      {data.length === 0 ? (
        <EmptyState testId="pnl-chart-empty">No snapshots yet — history builds every 30s.</EmptyState>
      ) : (
        <div data-testid="pnl-chart-plot" data-points={data.length} className="h-full w-full">
          <ResponsiveContainer width="100%" height="100%" minHeight={100}>
            <AreaChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1f2632" strokeDasharray="2 4" vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={fmtClock}
                stroke="#4f586a"
                tick={{ fontSize: 10, fontFamily: "ui-monospace, monospace" }}
                minTickGap={50}
              />
              <YAxis
                orientation="right"
                domain={["auto", "auto"]}
                tickFormatter={(v: number) => `$${axisMoney.format(v)}`}
                stroke="#4f586a"
                tick={{ fontSize: 10, fontFamily: "ui-monospace, monospace" }}
                width={76}
              />
              {base != null ? <ReferenceLine y={base} stroke="#3a4456" strokeDasharray="3 3" /> : null}
              <Tooltip
                isAnimationActive={false}
                contentStyle={{
                  background: "#11161e",
                  border: "1px solid #2a3240",
                  fontFamily: "ui-monospace, monospace",
                  fontSize: 11,
                }}
                labelFormatter={(v) => new Date(Number(v)).toLocaleTimeString("en-US", { hour12: false })}
                formatter={(v) => [fmtMoney(Number(v)), "Value"]}
              />
              <Area
                type="monotone"
                dataKey="v"
                stroke={stroke}
                strokeWidth={1.5}
                fill="url(#pnlFill)"
                dot={data.length === 1}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}
