"use client";

import { ResponsiveContainer, Treemap } from "recharts";
import Panel, { EmptyState } from "./Panel";
import type { Position } from "@/lib/types";
import { pnlColor } from "@/lib/portfolio";
import { fmtPct } from "@/lib/format";

interface HeatmapProps {
  positions: Position[];
  onSelect?: (ticker: string) => void;
}

interface CellProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  pnlPct?: number;
  weight?: number;
  depth?: number;
  onSelect?: (ticker: string) => void;
}

function Cell({ x = 0, y = 0, width = 0, height = 0, name, pnlPct = 0, weight = 0, depth, onSelect }: CellProps) {
  if (depth !== 1 || !name) return null;
  const showText = width > 36 && height > 22;
  const showDetail = width > 60 && height > 40;
  return (
    <g
      data-testid={`heatmap-cell-${name}`}
      data-pnl={pnlPct.toFixed(4)}
      style={{ cursor: onSelect ? "pointer" : undefined }}
      onClick={() => onSelect?.(name)}
    >
      <rect x={x} y={y} width={width} height={height} fill={pnlColor(pnlPct)} stroke="#0d1117" strokeWidth={2} />
      {showText ? (
        <text
          x={x + width / 2}
          y={y + height / 2 - (showDetail ? 6 : 0)}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#f1f5f9"
          fontSize={Math.min(14, Math.max(10, width / 6))}
          fontWeight={700}
          fontFamily="ui-monospace, monospace"
        >
          {name}
        </text>
      ) : null}
      {showDetail ? (
        <text
          x={x + width / 2}
          y={y + height / 2 + 10}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#e2e8f0"
          fillOpacity={0.85}
          fontSize={10}
          fontFamily="ui-monospace, monospace"
        >
          {fmtPct(pnlPct)} · {(weight * 100).toFixed(0)}%
        </text>
      ) : null}
    </g>
  );
}

export default function Heatmap({ positions, onSelect }: HeatmapProps) {
  const held = positions.filter((p) => p.market_value > 0);
  const total = held.reduce((s, p) => s + p.market_value, 0);
  const data = held.map((p) => ({
    name: p.ticker,
    size: p.market_value,
    pnlPct: p.unrealized_pnl_percent,
    weight: total > 0 ? p.market_value / total : 0,
  }));

  return (
    <Panel title="Heatmap" testId="heatmap" right={<span>size = weight · color = P&L %</span>} bodyClassName="p-1">
      {data.length === 0 ? (
        <EmptyState testId="heatmap-empty">No positions yet — buy something or ask FinAlly.</EmptyState>
      ) : (
        <ResponsiveContainer width="100%" height="100%" minHeight={100}>
          <Treemap
            data={data}
            dataKey="size"
            aspectRatio={4 / 3}
            isAnimationActive={false}
            content={<Cell onSelect={onSelect} />}
          />
        </ResponsiveContainer>
      )}
    </Panel>
  );
}
