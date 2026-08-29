"""AI client tests: response shape, context manager, and end-to-end
helpers. Uses httpx.MockTransport so no real OpenRouter call is made."""

import json

import httpx
import pytest

from lib.ai import (
    AIError,
    OpenRouterClient,
    classify_item,
    summarize_item,
)


def _client_with(handler):
    """OpenRouterClient with the underlying httpx transport swapped for a
    MockTransport. Matches the style in tests/test_discogs.py."""
    client = OpenRouterClient("test-key")
    client.close()
    client._http = httpx.Client(
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )
    return client


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "gen-1",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        },
    )


ITEM = {
    "title": "Kind Of Blue",
    "artist": "Miles Davis",
    "year": 1959,
    "genres": "Jazz",
    "discogs_styles": "Modal",
}


# -- lifecycle ---------------------------------------------------------------


def test_close_releases_underlying_http_client():
    client = OpenRouterClient("test-key")
    inner = client._http
    assert not inner.is_closed
    client.close()
    assert inner.is_closed


def test_context_manager_closes_client():
    with OpenRouterClient("test-key") as client:
        assert not client._http.is_closed
    assert client._http.is_closed


# -- complete(): happy path --------------------------------------------------


def test_complete_returns_stripped_string():
    seen_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(json.loads(request.content))
        return _chat_response("  hello there \n")

    with _client_with(handler) as client:
        result = client.complete("hi", system="be terse", max_tokens=10)
    assert result == "hello there"
    # payload assembled correctly
    assert seen_payloads[0]["model"].endswith(":online") is False
    assert seen_payloads[0]["max_tokens"] == 10
    assert seen_payloads[0]["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hi"},
    ]


def test_complete_appends_online_when_web_search():
    seen_model = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_model.append(json.loads(request.content)["model"])
        return _chat_response("ok")

    with _client_with(handler) as client:
        client.complete("hi", web_search=True)
    assert seen_model[0].endswith(":online")


# -- complete(): malformed responses become AIError --------------------------


def test_complete_raises_when_choices_empty():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with _client_with(handler) as client:
        with pytest.raises(AIError, match=r"no choices"):
            client.complete("hi")


def test_complete_raises_when_choices_missing():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "x"})

    with _client_with(handler) as client:
        with pytest.raises(AIError, match=r"no choices"):
            client.complete("hi")


def test_complete_raises_when_message_missing():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop"}]})

    with _client_with(handler) as client:
        with pytest.raises(AIError, match=r"no message"):
            client.complete("hi")


def test_complete_raises_when_message_content_not_string():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": None}}]},
        )

    with _client_with(handler) as client:
        with pytest.raises(AIError, match=r"not a string"):
            client.complete("hi")


def test_complete_raises_when_message_content_empty():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "length", "message": {"role": "assistant", "content": ""}}]},
        )

    with _client_with(handler) as client:
        with pytest.raises(AIError, match=r"empty response"):
            client.complete("hi")


def test_complete_raises_on_http_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream blew up")

    with _client_with(handler) as client:
        with pytest.raises(AIError, match=r"OpenRouter HTTP 500"):
            client.complete("hi")


# -- complete_json ----------------------------------------------------------


def test_complete_json_parses_object():
    def handler(_request: httpx.Request) -> httpx.Response:
        return _chat_response('{"folder": "jazz", "reason": "modal"}')

    with _client_with(handler) as client:
        assert client.complete_json("x") == {"folder": "jazz", "reason": "modal"}


def test_complete_json_raises_on_no_braces():
    def handler(_request: httpx.Request) -> httpx.Response:
        return _chat_response("no json here")

    with _client_with(handler) as client:
        with pytest.raises(AIError, match=r"no JSON"):
            client.complete_json("x")


# -- summarize_item / classify_item end-to-end -------------------------------


def test_summarize_item_happy_path():
    def handler(_request: httpx.Request) -> httpx.Response:
        return _chat_response('{"style": "modal, cool, jazz", "summary": "Modal jazz classic."}')

    with _client_with(handler) as client:
        result = summarize_item(client, ITEM, release_notes="Some release notes.")
    assert result == {"style": "modal, cool, jazz", "summary": "Modal jazz classic."}


def test_summarize_item_raises_on_missing_keys():
    def handler(_request: httpx.Request) -> httpx.Response:
        return _chat_response('{"style": "modal, cool"}')

    with _client_with(handler) as client:
        with pytest.raises(AIError, match=r"incomplete draft"):
            summarize_item(client, ITEM, release_notes="notes")


def test_classify_item_happy_path():
    def handler(_request: httpx.Request) -> httpx.Response:
        return _chat_response('{"folder": "jazz", "reason": "modal jazz record"}')

    with _client_with(handler) as client:
        result = classify_item(client, ITEM, ["jazz", "rock", "Uncategorized"])
    assert result == {"folder": "jazz", "reason": "modal jazz record"}


def test_classify_item_raises_on_missing_keys():
    def handler(_request: httpx.Request) -> httpx.Response:
        return _chat_response('{"folder": "jazz"}')

    with _client_with(handler) as client:
        with pytest.raises(AIError, match=r"incomplete classify"):
            classify_item(client, ITEM, ["jazz", "rock"])
