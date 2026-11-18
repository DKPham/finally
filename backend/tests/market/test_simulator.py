"""Tests for GBMSimulator."""

import math
import random

import numpy as np
import pytest

from app.market.seed_prices import SEED_PRICES
from app.market.simulator import GBMSimulator


class TestGBMSimulator:
    """Unit tests for the GBM price simulator."""

    def test_step_returns_all_tickers(self):
        """Test that step() returns prices for all tickers."""
        sim = GBMSimulator(tickers=["AAPL", "GOOGL"])
        result = sim.step()
        assert set(result.keys()) == {"AAPL", "GOOGL"}

    def test_prices_are_positive(self):
        """GBM prices can never go negative (exp() is always positive)."""
        sim = GBMSimulator(tickers=["AAPL"])
        for _ in range(10_000):
            prices = sim.step()
            assert prices["AAPL"] > 0

    def test_initial_prices_match_seeds(self):
        """Test that initial prices match seed prices."""
        sim = GBMSimulator(tickers=["AAPL"])
        # Before any step, price should be the seed price
        assert sim.get_price("AAPL") == SEED_PRICES["AAPL"]

    def test_add_ticker(self):
        """Test adding a ticker dynamically."""
        sim = GBMSimulator(tickers=["AAPL"])
        sim.add_ticker("TSLA")
        result = sim.step()
        assert "TSLA" in result

    def test_remove_ticker(self):
        """Test removing a ticker."""
        sim = GBMSimulator(tickers=["AAPL", "GOOGL"])
        sim.remove_ticker("GOOGL")
        result = sim.step()
        assert "GOOGL" not in result
        assert "AAPL" in result

    def test_add_duplicate_is_noop(self):
        """Test that adding a duplicate ticker is a no-op."""
        sim = GBMSimulator(tickers=["AAPL"])
        sim.add_ticker("AAPL")
        assert len(sim._tickers) == 1

    def test_remove_nonexistent_is_noop(self):
        """Test that removing a non-existent ticker is a no-op."""
        sim = GBMSimulator(tickers=["AAPL"])
        sim.remove_ticker("NOPE")  # Should not raise

    def test_unknown_ticker_gets_random_seed_price(self):
        """Test that unknown tickers get random seed prices."""
        sim = GBMSimulator(tickers=["ZZZZ"])
        price = sim.get_price("ZZZZ")
        assert price is not None
        assert 50.0 <= price <= 300.0

    def test_empty_step(self):
        """Test stepping with no tickers."""
        sim = GBMSimulator(tickers=[])
        result = sim.step()
        assert result == {}

    def test_prices_change_over_time(self):
        """After many steps, prices should have drifted from their seeds."""
        sim = GBMSimulator(tickers=["AAPL"])
        initial_price = sim.get_price("AAPL")

        for _ in range(1000):
            sim.step()

        final_price = sim.get_price("AAPL")
        # Price should have changed (extremely unlikely to be exactly the seed)
        assert final_price != initial_price

    def test_cholesky_rebuilds_on_add(self):
        """Test that Cholesky matrix is rebuilt when tickers are added."""
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim._cholesky is None  # Only 1 ticker, no correlation matrix
        sim.add_ticker("GOOGL")
        assert sim._cholesky is not None  # Now 2 tickers, matrix exists

    def test_cholesky_none_with_one_ticker(self):
        """Test that Cholesky is None with only one ticker."""
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim._cholesky is None

    def test_get_price_returns_none_for_unknown(self):
        """Test that get_price returns None for unknown ticker."""
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim.get_price("UNKNOWN") is None

    def test_pairwise_correlation_tech_stocks(self):
        """Test that tech stocks have high correlation."""
        corr = GBMSimulator._pairwise_correlation("AAPL", "GOOGL")
        assert corr == 0.6

    def test_pairwise_correlation_finance_stocks(self):
        """Test that finance stocks have moderate correlation."""
        corr = GBMSimulator._pairwise_correlation("JPM", "V")
        assert corr == 0.5

    def test_pairwise_correlation_tsla(self):
        """Test that TSLA has lower correlation with everything."""
        corr = GBMSimulator._pairwise_correlation("TSLA", "AAPL")
        assert corr == 0.3
        corr = GBMSimulator._pairwise_correlation("TSLA", "JPM")
        assert corr == 0.3

    def test_pairwise_correlation_cross_sector(self):
        """Test cross-sector correlation."""
        corr = GBMSimulator._pairwise_correlation("AAPL", "JPM")
        assert corr == 0.3

    def test_default_dt_is_reasonable(self):
        """Test that default dt is a reasonable small value."""
        assert 0 < GBMSimulator.DEFAULT_DT < 0.0001

    def test_prices_rounded_to_two_decimals(self):
        """Test that prices are rounded to 2 decimal places."""
        sim = GBMSimulator(tickers=["AAPL"])
        result = sim.step()
        price_str = str(result["AAPL"])
        # Check that we have at most 2 decimal places
        if "." in price_str:
            decimal_part = price_str.split(".")[1]
            assert len(decimal_part) <= 2


class TestGBMStatistics:
    """The engine's maths, checked empirically (events off, large dt, seeded)."""

    @staticmethod
    def _log_returns(sim: GBMSimulator, steps: int) -> dict[str, np.ndarray]:
        prev = {t: sim.get_price(t) for t in sim.get_tickers()}
        out: dict[str, list[float]] = {t: [] for t in prev}
        for _ in range(steps):
            sim.step()
            for t in prev:
                price = sim.get_price(t)
                out[t].append(math.log(price / prev[t]))
                prev[t] = price
        return {t: np.array(v) for t, v in out.items()}

    def test_volatility_and_drift_match_parameters(self):
        np.random.seed(0)
        random.seed(0)
        dt = 1 / 252
        sim = GBMSimulator(["AAPL"], dt=dt, event_probability=0)
        r = self._log_returns(sim, 20_000)["AAPL"]
        sigma, mu = 0.22, 0.05
        assert r.std() == pytest.approx(sigma * math.sqrt(dt), rel=0.03)
        assert r.mean() == pytest.approx(
            (mu - sigma**2 / 2) * dt, abs=3 * r.std() / math.sqrt(len(r))
        )

    def test_sector_correlations(self):
        np.random.seed(1)
        random.seed(1)
        sim = GBMSimulator(["AAPL", "MSFT", "TSLA", "JPM", "V"], dt=1 / 252, event_probability=0)
        r = self._log_returns(sim, 20_000)
        corr = lambda a, b: np.corrcoef(r[a], r[b])[0, 1]  # noqa: E731
        assert corr("AAPL", "MSFT") == pytest.approx(0.6, abs=0.05)
        assert corr("AAPL", "TSLA") == pytest.approx(0.3, abs=0.05)
        assert corr("JPM", "V") == pytest.approx(0.5, abs=0.05)
        assert corr("AAPL", "JPM") == pytest.approx(0.3, abs=0.05)

    def test_prices_stay_positive_and_finite_long_run(self):
        np.random.seed(2)
        random.seed(2)
        sim = GBMSimulator(list(SEED_PRICES), event_probability=0.01)
        for _ in range(10_000):
            prices = sim.step()
        assert all(p > 0 and math.isfinite(p) for p in prices.values())

    def test_events_jump_2_to_5_percent(self):
        random.seed(3)
        np.random.seed(3)
        # dt=0 removes diffusion, so any move is purely the shock event
        sim = GBMSimulator(["AAPL"], dt=0.0, event_probability=1.0)
        for _ in range(200):
            before = sim.get_price("AAPL")
            sim.step()
            move = abs(sim.get_price("AAPL") / before - 1)
            assert 0.02 - 1e-9 <= move <= 0.05 + 1e-9

    def test_no_events_when_probability_zero(self):
        sim = GBMSimulator(["AAPL"], dt=0.0, event_probability=0.0)
        sim.step()
        assert sim.get_price("AAPL") == SEED_PRICES["AAPL"]


class TestGBMStructure:
    def test_full_default_set_cholesky(self):
        sim = GBMSimulator(list(SEED_PRICES))
        assert sim._cholesky.shape == (10, 10)

    def test_forty_tickers_supported(self):
        sim = GBMSimulator([f"T{i}" for i in range(40)])
        assert sim._cholesky.shape == (40, 40)
        assert len(sim.step()) == 40

    def test_non_positive_definite_falls_back_to_independent(self, monkeypatch):
        sim = GBMSimulator(["AAPL"])
        monkeypatch.setattr(GBMSimulator, "_pairwise_correlation", staticmethod(lambda a, b: 1.5))
        sim.add_ticker("MSFT")
        assert sim._cholesky is None
        assert len(sim.step()) == 2

    def test_seeded_tickers_do_not_consume_random_draws(self):
        random.seed(42)
        GBMSimulator(list(SEED_PRICES))
        after_seeded = random.random()
        random.seed(42)
        assert random.random() == after_seeded

    def test_unknown_ticker_uses_default_params_copy(self):
        sim = GBMSimulator(["ZZZZ"])
        sim._params["ZZZZ"]["sigma"] = 9.9
        from app.market.seed_prices import DEFAULT_PARAMS

        assert DEFAULT_PARAMS["sigma"] == 0.25

    def test_readd_after_remove(self):
        sim = GBMSimulator(["AAPL", "MSFT"])
        sim.remove_ticker("MSFT")
        sim.add_ticker("MSFT")
        assert sim.get_tickers() == ["AAPL", "MSFT"]
        assert sim._cholesky.shape == (2, 2)
