import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Header from "./Header";
import PositionsTable from "./PositionsTable";
import Heatmap from "./Heatmap";
import PnlChart from "./PnlChart";
import { portfolioFixture } from "@/test/fixtures";

describe("Header", () => {
  it("shows total value, cash and the connection status", () => {
    render(<Header totalValue={10054.95} cashBalance={8094.8} unrealizedPnl={54.95} status="connected" />);
    expect(screen.getByTestId("total-value")).toHaveTextContent("$10,054.95");
    expect(screen.getByTestId("cash-balance")).toHaveTextContent("$8,094.80");
    expect(screen.getByTestId("unrealized-pnl")).toHaveTextContent("+$54.95");
    expect(screen.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
  });

  it.each(["reconnecting", "disconnected"] as const)("reflects %s", (status) => {
    render(<Header totalValue={null} cashBalance={null} unrealizedPnl={null} status={status} />);
    expect(screen.getByTestId("connection-status")).toHaveAttribute("data-status", status);
    expect(screen.getByTestId("total-value")).toHaveTextContent("—");
  });
});

describe("PositionsTable", () => {
  it("renders position rows", () => {
    render(<PositionsTable positions={portfolioFixture.positions} />);
    expect(screen.getByTestId("position-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("position-qty-AAPL")).toHaveTextContent("10");
    expect(screen.getByTestId("position-price-AAPL")).toHaveTextContent("200.00");
    expect(screen.getByTestId("position-pnl-AAPL")).toHaveTextContent("+$100.00");
  });
  it("shows the empty hint", () => {
    render(<PositionsTable positions={[]} />);
    expect(screen.getByTestId("positions-empty")).toHaveTextContent("No positions yet");
  });
});

describe("Heatmap / PnlChart empty states", () => {
  it("heatmap hint with no positions", () => {
    render(<Heatmap positions={[]} />);
    expect(screen.getByTestId("heatmap-empty")).toHaveTextContent("buy something or ask FinAlly");
  });
  it("pnl chart hint with no history, plot with data", () => {
    const { rerender } = render(<PnlChart history={[]} />);
    expect(screen.getByTestId("pnl-chart-empty")).toBeInTheDocument();
    rerender(
      <PnlChart
        history={[
          { recorded_at: "2026-11-16T14:03:00Z", total_value: 10000 },
          { recorded_at: "2026-11-16T14:03:30Z", total_value: 10050 },
        ]}
      />,
    );
    expect(screen.getByTestId("pnl-chart-plot")).toHaveAttribute("data-points", "2");
  });
});
