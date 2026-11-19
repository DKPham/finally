import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Watchlist from "./Watchlist";
import { tick, watchlistFixture } from "@/test/fixtures";

function setup(overrides: Partial<Parameters<typeof Watchlist>[0]> = {}) {
  const props = {
    items: watchlistFixture,
    latest: {},
    history: {},
    selected: "AAPL",
    onAdd: vi.fn().mockResolvedValue(undefined),
    onRemove: vi.fn().mockResolvedValue(undefined),
    ...overrides,
    onSelect: vi.fn(),
  };
  render(<Watchlist {...props} />);
  return props;
}

describe("Watchlist", () => {
  it("renders a row per ticker in order with API prices as fallback", () => {
    setup();
    const rows = screen.getAllByTestId(/^watchlist-row-/);
    expect(rows.map((r) => r.dataset.testid)).toEqual(["watchlist-row-AAPL", "watchlist-row-MSFT"]);
    expect(screen.getByTestId("watchlist-price-AAPL")).toHaveTextContent("200.00");
    expect(screen.getByTestId("watchlist-change-AAPL")).toHaveTextContent("+1.20%");
    expect(screen.getByTestId("watchlist-price-MSFT")).toHaveTextContent("—");
    expect(screen.getByTestId("watchlist-row-AAPL")).toHaveAttribute("data-selected", "true");
  });

  it("prefers live SSE prices and session change", () => {
    setup({ latest: { MSFT: tick("MSFT", 404, 400, 400) } });
    expect(screen.getByTestId("watchlist-price-MSFT")).toHaveTextContent("404.00");
    expect(screen.getByTestId("watchlist-change-MSFT")).toHaveTextContent("+1.00%");
  });

  it("selects on click and removes via the × control without selecting", async () => {
    const props = setup();
    await userEvent.click(screen.getByTestId("watchlist-row-MSFT"));
    expect(props.onSelect).toHaveBeenCalledWith("MSFT");
    props.onSelect.mockClear();
    await userEvent.click(screen.getByTestId("watchlist-remove-AAPL"));
    expect(props.onRemove).toHaveBeenCalledWith("AAPL");
    expect(props.onSelect).not.toHaveBeenCalled();
  });

  it("adds an uppercased ticker and clears the input", async () => {
    const props = setup();
    const input = screen.getByTestId("watchlist-add-input");
    await userEvent.type(input, "pypl");
    await userEvent.click(screen.getByTestId("watchlist-add-button"));
    expect(props.onAdd).toHaveBeenCalledWith("PYPL");
    await waitFor(() => expect(input).toHaveValue(""));
  });

  it("shows server errors inline", async () => {
    setup({ onAdd: vi.fn().mockRejectedValue(new Error("AAPL is already on the watchlist")) });
    await userEvent.type(screen.getByTestId("watchlist-add-input"), "AAPL{enter}");
    expect(await screen.findByTestId("watchlist-error")).toHaveTextContent("already on the watchlist");
  });

  it("rejects invalid tickers client-side", async () => {
    const props = setup();
    await userEvent.type(screen.getByTestId("watchlist-add-input"), "1AB{enter}");
    expect(await screen.findByTestId("watchlist-error")).toHaveTextContent("not a valid ticker");
    expect(props.onAdd).not.toHaveBeenCalled();
  });

  it("shows an empty state", () => {
    setup({ items: [] });
    expect(screen.getByTestId("watchlist-empty")).toBeInTheDocument();
  });
});
