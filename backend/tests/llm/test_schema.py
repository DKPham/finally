import pytest

from app.llm.schema import LLMResponse, parse_llm_response


def test_full_response():
    r = parse_llm_response(
        '{"message": "Buying", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],'
        ' "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]}'
    )
    assert r.message == "Buying"
    assert r.trades[0].ticker == "AAPL" and r.trades[0].side == "buy"
    assert r.trades[0].quantity == 10.0
    assert r.watchlist_changes[0].action == "add"


def test_message_only_defaults_empty_lists():
    r = parse_llm_response('{"message": "Hi"}')
    assert r.trades == [] and r.watchlist_changes == []


def test_null_lists_treated_as_empty():
    r = parse_llm_response('{"message": "Hi", "trades": null, "watchlist_changes": null}')
    assert r.trades == [] and r.watchlist_changes == []


def test_fractional_quantity():
    r = parse_llm_response(
        '{"message": "m", "trades": [{"ticker": "NVDA", "side": "sell", "quantity": 0.5}],'
        ' "watchlist_changes": []}'
    )
    assert r.trades[0].quantity == 0.5


def test_markdown_fenced_json():
    r = parse_llm_response('```json\n{"message": "Hi", "trades": [], "watchlist_changes": []}\n```')
    assert r.message == "Hi"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "not json",
        "[1, 2]",
        '{"trades": []}',  # missing message
        '{"message": "m", "trades": [{"ticker": "AAPL", "side": "hold", "quantity": 1}]}',
        '{"message": "m", "trades": [{"ticker": "AAPL", "side": "buy"}]}',
        '{"message": "m", "watchlist_changes": [{"ticker": "AAPL", "action": "toggle"}]}',
        '{"message": "m", "trades": "AAPL"}',
    ],
)
def test_malformed_raises_value_error(raw):
    with pytest.raises(ValueError):
        parse_llm_response(raw)


def test_json_schema_has_required_fields():
    schema = LLMResponse.model_json_schema()
    assert set(schema["required"]) == {"message", "trades", "watchlist_changes"}
