"use client";

import { memo } from "react";
import { Line, LineChart, YAxis } from "recharts";
import type { PricePoint } from "@/lib/types";

interface SparklineProps {
  points: PricePoint[] | undefined;
  width?: number;
  height?: number;
  up?: boolean;
}

function Sparkline({ points, width = 76, height = 24, up = true }: SparklineProps) {
  if (!points || points.length < 2) {
    return (
      <div style={{ width, height }} className="flex items-center">
        <div className="h-px w-full bg-ink-600" />
      </div>
    );
  }
  return (
    <LineChart width={width} height={height} data={points} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
      <YAxis hide domain={["dataMin", "dataMax"]} />
      <Line
        type="monotone"
        dataKey="price"
        stroke={up ? "#22c55e" : "#ef4444"}
        strokeWidth={1.25}
        dot={false}
        isAnimationActive={false}
      />
    </LineChart>
  );
}

export default memo(Sparkline);
