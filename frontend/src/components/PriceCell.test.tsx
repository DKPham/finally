import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PriceCell, { FLASH_HOLD_MS } from "./PriceCell";

describe("PriceCell", () => {
  it("renders the formatted price without a flash initially", () => {
    render(<PriceCell price={190.5} testId="p" />);
    const el = screen.getByTestId("p");
    expect(el).toHaveTextContent("190.50");
    expect(el).not.toHaveClass("flash-up");
    expect(el).not.toHaveClass("flash-down");
  });

  it("flashes green on uptick and clears after the hold", () => {
    vi.useFakeTimers();
    const { rerender } = render(<PriceCell price={190} testId="p" />);
    rerender(<PriceCell price={191} testId="p" />);
    const el = screen.getByTestId("p");
    expect(el).toHaveClass("flash-up");
    expect(el).toHaveAttribute("data-flash", "up");
    act(() => vi.advanceTimersByTime(FLASH_HOLD_MS + 5));
    expect(el).not.toHaveClass("flash-up");
  });

  it("flashes red on downtick", () => {
    const { rerender } = render(<PriceCell price={190} testId="p" />);
    rerender(<PriceCell price={189} testId="p" />);
    expect(screen.getByTestId("p")).toHaveClass("flash-down");
  });

  it("does not flash when the price is unchanged or first arrives", () => {
    const { rerender } = render(<PriceCell price={null} testId="p" />);
    expect(screen.getByTestId("p")).toHaveTextContent("—");
    rerender(<PriceCell price={190} testId="p" />);
    expect(screen.getByTestId("p")).not.toHaveAttribute("data-flash");
    rerender(<PriceCell price={190} testId="p" />);
    expect(screen.getByTestId("p")).not.toHaveAttribute("data-flash");
  });
});
