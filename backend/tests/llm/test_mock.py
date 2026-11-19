import pytest

from app.llm.client import is_mock_mode, mock_response


@pytest.mark.parametrize(
    "msg,qty,ticker",
    [("buy 5 NVDA", 5.0, "NVDA"), ("Buy 1 aapl", 1.0, "AAPL"), ("please BUY 2.5 tsla now", 2.5, "TSLA")],
)
def test_buy(msg, qty, ticker):
    r = mock_response(msg)
    assert r.message == f"Buying {msg.split()[msg.lower().split().index('buy') + 1]} {ticker}."
    assert len(r.trades) == 1 and r.watchlist_changes == []
    t = r.trades[0]
    assert (t.ticker, t.side, t.quantity) == (ticker, "buy", qty)


def test_buy_message_exact():
    assert mock_response("buy 1 AAPL").message == "Buying 1 AAPL."


def test_sell():
    r = mock_response("sell 3 msft")
    assert r.message == "Selling 3 MSFT."
    assert r.trades[0].side == "sell" and r.trades[0].quantity == 3.0
    assert r.trades[0].ticker == "MSFT"


def test_watch():
    r = mock_response("watch pypl")
    assert r.message == "Adding PYPL to your watchlist."
    assert r.trades == []
    assert [(w.ticker, w.action) for w in r.watchlist_changes] == [("PYPL", "add")]


def test_unwatch_not_confused_with_watch():
    r = mock_response("Unwatch PYPL")
    assert r.message == "Removing PYPL from your watchlist."
    assert [(w.ticker, w.action) for w in r.watchlist_changes] == [("PYPL", "remove")]


@pytest.mark.parametrize("msg", ["hello", "how is my portfolio?", "buy NVDA", "buy some 5"])
def test_fallback(msg):
    r = mock_response(msg)
    assert r.message == "This is a mock response from FinAlly."
    assert r.trades == [] and r.watchlist_changes == []


def test_is_mock_mode(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "TRUE")
    assert is_mock_mode()
    monkeypatch.setenv("LLM_MOCK", "false")
    assert not is_mock_mode()
    monkeypatch.delenv("LLM_MOCK")
    assert not is_mock_mode()
