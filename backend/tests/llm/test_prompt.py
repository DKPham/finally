from app.llm.prompt import SYSTEM_PROMPT, build_messages, build_portfolio_context


def test_context_includes_positions_and_watchlist(broker):
    broker.positions = {"NVDA": 2}
    ctx = build_portfolio_context(broker.get_portfolio(), broker.list_watchlist())
    assert "Cash: $10,000.00" in ctx
    assert "NVDA: qty 2" in ctx
    assert "Watchlist (2/30)" in ctx
    assert "AAPL: $190.00" in ctx


def test_context_empty_portfolio():
    ctx = build_portfolio_context(
        {"cash_balance": 10000.0, "positions_value": 0.0, "total_value": 10000.0,
         "unrealized_pnl": 0.0, "positions": []},
        [{"ticker": "ZZZ", "price": None, "session_change_percent": None}],
    )
    assert "Positions: none" in ctx
    assert "ZZZ: n/a" in ctx


def test_build_messages_order_and_action_results():
    history = [
        {"role": "user", "content": "buy 100 TSLA", "actions": None},
        {"role": "assistant", "content": "Buying 100 TSLA.",
         "actions": [{"type": "trade", "ticker": "TSLA", "status": "failed",
                      "error": "Insufficient cash"}]},
    ]
    msgs = build_messages(history, "CTX", "why did it fail?")
    assert msgs[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert "FinAlly" in SYSTEM_PROMPT
    assert msgs[1]["role"] == "user"
    assert "[Action results:" in msgs[2]["content"]
    assert "Insufficient cash" in msgs[2]["content"]
    assert msgs[-2] == {"role": "system", "content": "CTX"}
    assert msgs[-1] == {"role": "user", "content": "why did it fail?"}


def test_history_capped_at_20():
    history = [{"role": "user", "content": str(i), "actions": None} for i in range(30)]
    msgs = build_messages(history, "CTX", "new")
    convo = msgs[1:-2]
    assert len(convo) == 20
    assert convo[0]["content"] == "10"
