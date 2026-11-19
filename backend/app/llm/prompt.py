"""System prompt, portfolio context and conversation history for the LLM."""

from __future__ import annotations

import json

HISTORY_LIMIT = 20

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant inside a simulated trading \
workstation. The user trades a virtual portfolio with fake money; market orders fill \
instantly at the current price with no fees.

Your job:
- Analyze portfolio composition, risk concentration and P&L using the live data provided.
- Suggest trades with brief, concrete reasoning.
- Execute trades when the user asks for them or agrees to a suggestion, by listing them \
in `trades`. Do not execute trades the user has not asked for or agreed to.
- Manage the watchlist proactively via `watchlist_changes` (e.g. add a ticker the user \
is asking about).
- Be concise and data-driven: use numbers, keep replies short.

Rules:
- Always respond with valid JSON matching the schema: `message` (string), `trades` \
(list of {ticker, side: "buy"|"sell", quantity > 0}), `watchlist_changes` (list of \
{ticker, action: "add"|"remove"}). Use empty lists when there is nothing to do.
- Your message is written before the actions run, so phrase it as what you are doing \
(e.g. "Buying 5 NVDA."), not as a confirmed result. The actual outcome of each action \
is shown to the user separately and appears in the conversation history as \
"[Action results: ...]" so you can follow up on failures.
- Buys need enough cash (quantity x current price); sells cannot exceed the held quantity. \
Fractional shares are allowed. Tickers are US stock symbols in uppercase.
- The watchlist holds at most 30 tickers.
"""


def _money(x: float | None) -> str:
    return "n/a" if x is None else f"${x:,.2f}"


def build_portfolio_context(portfolio: dict, watchlist: list[dict]) -> str:
    """Render the live portfolio and watchlist as compact text for the LLM."""
    lines = [
        "Current portfolio state (live):",
        f"- Cash: {_money(portfolio.get('cash_balance'))}",
        f"- Positions value: {_money(portfolio.get('positions_value'))}",
        f"- Total value: {_money(portfolio.get('total_value'))}",
        f"- Unrealized P&L: {_money(portfolio.get('unrealized_pnl'))}",
    ]
    positions = portfolio.get("positions") or []
    total = portfolio.get("total_value") or 0.0
    if positions:
        lines.append("Positions:")
        for p in positions:
            weight = (p.get("market_value", 0.0) / total * 100) if total else 0.0
            lines.append(
                f"- {p['ticker']}: qty {p['quantity']:g}, avg cost {_money(p.get('avg_cost'))}, "
                f"price {_money(p.get('current_price'))}, value {_money(p.get('market_value'))} "
                f"({weight:.1f}% of portfolio), P&L {_money(p.get('unrealized_pnl'))} "
                f"({p.get('unrealized_pnl_percent', 0.0):+.2f}%)"
            )
    else:
        lines.append("Positions: none")
    if watchlist:
        lines.append(f"Watchlist ({len(watchlist)}/30):")
        for w in watchlist:
            chg = w.get("session_change_percent")
            chg_s = "n/a" if chg is None else f"{chg:+.2f}%"
            lines.append(f"- {w['ticker']}: {_money(w.get('price'))} (session {chg_s})")
    else:
        lines.append("Watchlist: empty")
    return "\n".join(lines)


def _history_content(msg: dict) -> str:
    content = msg.get("content") or ""
    actions = msg.get("actions")
    if msg.get("role") == "assistant" and actions:
        content += "\n\n[Action results: " + json.dumps(actions) + "]"
    return content


def build_messages(history: list[dict], context: str, user_message: str) -> list[dict]:
    """Assemble the chat messages: system prompt, prior turns, live context, new message.

    `history` is oldest-first and must NOT include the new user message.
    """
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history[-HISTORY_LIMIT:]:
        if msg.get("role") in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": _history_content(msg)})
    messages.append({"role": "system", "content": context})
    messages.append({"role": "user", "content": user_message})
    return messages
