import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import TradeBar from "./TradeBar";
import type { Trade } from "@/lib/types";

const trade: Trade = { id: "t1", ticker: "AAPL", side: "buy", quantity: 10, price: 190.52, executed_at: "" };

function setup(onTrade = vi.fn().mockResolvedValue(trade)) {
  render(<TradeBar selectedTicker="AAPL" priceFor={() => 190} cash={10000} onTrade={onTrade} />);
  return onTrade;
}

describe("TradeBar", () => {
  it("prefills the selected ticker and submits a buy", async () => {
    const onTrade = setup();
    expect(screen.getByTestId("trade-ticker")).toHaveValue("AAPL");
    await userEvent.type(screen.getByTestId("trade-quantity"), "10");
    await userEvent.click(screen.getByTestId("trade-buy"));
    expect(onTrade).toHaveBeenCalledWith("AAPL", 10, "buy");
    expect(await screen.findByTestId("trade-success")).toHaveTextContent("Bought 10 AAPL @ $190.52");
  });

  it("submits a sell", async () => {
    const onTrade = setup(vi.fn().mockResolvedValue({ ...trade, side: "sell", quantity: 2 }));
    await userEvent.type(screen.getByTestId("trade-quantity"), "2");
    await userEvent.click(screen.getByTestId("trade-sell"));
    expect(onTrade).toHaveBeenCalledWith("AAPL", 2, "sell");
    expect(await screen.findByTestId("trade-success")).toHaveTextContent("Sold 2 AAPL");
  });

  it("validates quantity client-side", async () => {
    const onTrade = setup();
    await userEvent.click(screen.getByTestId("trade-buy"));
    expect(screen.getByTestId("trade-error")).toHaveTextContent("Quantity must be greater than 0");
    expect(onTrade).not.toHaveBeenCalled();
  });

  it("shows API errors inline", async () => {
    setup(vi.fn().mockRejectedValue(new Error("Insufficient cash: need $1,905.20, have $1,200.00")));
    await userEvent.type(screen.getByTestId("trade-quantity"), "10");
    await userEvent.click(screen.getByTestId("trade-buy"));
    expect(await screen.findByTestId("trade-error")).toHaveTextContent("Insufficient cash");
  });
});
