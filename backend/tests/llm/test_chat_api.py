"""HTTP-level tests for app.api.chat with fake services."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chat import router
from app.llm import chat as chat_mod

pytestmark = pytest.mark.usefixtures("temp_db")


@pytest.fixture
def http(monkeypatch, broker):
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.setattr(chat_mod, "default_services", broker.services)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_post_chat_and_history(http, broker):
    r = http.post("/api/chat", json={"message": "buy 2 NVDA"})
    assert r.status_code == 200
    body = r.json()
    assert body["message"] == "Buying 2 NVDA."
    assert body["actions"][0]["status"] == "executed"
    assert broker.positions == {"NVDA": 2.0}

    h = http.get("/api/chat/history")
    assert h.status_code == 200
    rows = h.json()
    assert [x["role"] for x in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "buy 2 NVDA" and rows[0]["actions"] is None
    assert rows[1]["actions"] == body["actions"]


def test_failed_action_still_200(http):
    r = http.post("/api/chat", json={"message": "sell 5 TSLA"})
    assert r.status_code == 200
    a = r.json()["actions"][0]
    assert a["status"] == "failed" and a["price"] is None and a["error"]


@pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": 5}])
def test_malformed_request_422(http, payload):
    assert http.post("/api/chat", json=payload).status_code == 422


def test_history_empty(http):
    assert http.get("/api/chat/history").json() == []
