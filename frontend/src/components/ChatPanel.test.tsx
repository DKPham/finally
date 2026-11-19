import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ChatPanel, { describeAction } from "./ChatPanel";
import type { ChatMessage } from "@/lib/types";

const messages: ChatMessage[] = [
  { id: "1", role: "user", content: "Buy 5 NVDA", actions: null, created_at: "" },
  {
    id: "2",
    role: "assistant",
    content: "Done — bought 5 NVDA.",
    actions: [
      { type: "trade", ticker: "NVDA", side: "buy", quantity: 5, status: "executed", price: 890.1, error: null },
      { type: "trade", ticker: "TSLA", side: "sell", quantity: 100, status: "failed", error: "you hold 20" },
      { type: "watchlist", ticker: "PYPL", action: "add", status: "failed", error: "PYPL is already on the watchlist" },
    ],
    created_at: "",
  },
];

function setup(overrides: Partial<Parameters<typeof ChatPanel>[0]> = {}) {
  const props = { open: true, onToggle: vi.fn(), messages, loading: false, onSend: vi.fn(), ...overrides };
  render(<ChatPanel {...props} />);
  return props;
}

describe("describeAction", () => {
  it("describes executed and failed actions", () => {
    expect(describeAction(messages[1].actions![0])).toBe("Bought 5 NVDA @ $890.10");
    expect(describeAction(messages[1].actions![1])).toBe("Sell 100 TSLA failed: you hold 20");
    expect(describeAction({ type: "watchlist", ticker: "PYPL", action: "add", status: "executed" })).toBe(
      "Added PYPL to watchlist",
    );
    expect(describeAction({ type: "watchlist", ticker: "PYPL", action: "remove", status: "executed" })).toBe(
      "Removed PYPL from watchlist",
    );
  });
});

describe("ChatPanel", () => {
  it("renders messages with roles and inline action results", () => {
    setup();
    const msgs = screen.getAllByTestId("chat-message");
    expect(msgs.map((m) => m.dataset.role)).toEqual(["user", "assistant"]);
    const actions = screen.getAllByTestId("chat-action");
    expect(actions).toHaveLength(3);
    expect(actions[0]).toHaveAttribute("data-status", "executed");
    expect(actions[0]).toHaveTextContent("✓Bought 5 NVDA @ $890.10");
    expect(actions[1]).toHaveAttribute("data-status", "failed");
    expect(actions[1]).toHaveTextContent("✗Sell 100 TSLA failed: you hold 20");
  });

  it("shows a loading indicator and disables send while waiting", async () => {
    setup({ loading: true });
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
    await userEvent.type(screen.getByTestId("chat-input"), "hi");
    expect(screen.getByTestId("chat-send")).toBeDisabled();
  });

  it("sends trimmed text on submit and clears the input", async () => {
    const props = setup({ messages: [] });
    const input = screen.getByTestId("chat-input");
    await userEvent.type(input, "  buy 1 AAPL  {enter}");
    expect(props.onSend).toHaveBeenCalledWith("buy 1 AAPL");
    expect(input).toHaveValue("");
    expect(screen.queryByTestId("chat-loading")).not.toBeInTheDocument();
  });

  it("collapses to a toggle", async () => {
    const props = setup({ open: false });
    expect(screen.queryByTestId("chat-input")).not.toBeInTheDocument();
    expect(screen.getByTestId("chat-panel")).toHaveAttribute("data-open", "false");
    await userEvent.click(screen.getByTestId("chat-toggle"));
    expect(props.onToggle).toHaveBeenCalled();
  });
});
