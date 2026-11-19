"""TestClient fixture: real app + lifespan, tmp DB_PATH, deterministic FakeSource."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from tests.services.fakes import DEFAULT_PRICES, FakeSource


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("LLM_MOCK", "true")
    holder = {}

    def factory(cache):
        holder["source"] = FakeSource(cache, DEFAULT_PRICES)
        return holder["source"]

    monkeypatch.setattr(main_module, "create_market_data_source", factory)
    with TestClient(main_module.create_app()) as c:
        c.source = holder["source"]
        yield c
