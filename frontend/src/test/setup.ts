import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { MockEventSource } from "./mockEventSource";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverMock;
(globalThis as unknown as { EventSource: unknown }).EventSource = MockEventSource;

afterEach(() => {
  cleanup();
  MockEventSource.reset();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

// jsdom has no layout, so Recharts' ResponsiveContainer measures 0×0 and warns; silence that noise only.
const origWarn = console.warn;
console.warn = (...args: unknown[]) => {
  if (typeof args[0] === "string" && args[0].includes("of chart should be greater than 0")) return;
  origWarn(...args);
};
