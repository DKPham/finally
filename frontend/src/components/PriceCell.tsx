"use client";

import { useEffect, useRef, useState } from "react";
import { fmtPrice } from "@/lib/format";

export const FLASH_HOLD_MS = 150;

interface PriceCellProps {
  price: number | null | undefined;
  testId?: string;
  className?: string;
}

/** Shows a price and briefly flashes green/red when it changes; the CSS transition fades it out. */
export default function PriceCell({ price, testId, className = "" }: PriceCellProps) {
  const prev = useRef<number | null | undefined>(price);
  const [flash, setFlash] = useState<"up" | "down" | null>(null);

  useEffect(() => {
    const before = prev.current;
    prev.current = price;
    if (before == null || price == null || before === price) return;
    setFlash(price > before ? "up" : "down");
    const t = setTimeout(() => setFlash(null), FLASH_HOLD_MS);
    return () => clearTimeout(t);
  }, [price]);

  return (
    <span
      data-testid={testId}
      data-flash={flash ?? undefined}
      className={`price-cell inline-block rounded-sm px-1 font-mono tabular-nums ${
        flash === "up" ? "flash-up" : flash === "down" ? "flash-down" : ""
      } ${className}`}
    >
      {fmtPrice(price)}
    </span>
  );
}
