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


def test_complete_json_greedy_regex_with_two_objects():
    r"""Documents the current behavior of ``complete_json`` when the model
    response contains two JSON-like braces (e.g. two objects, or one
    object plus noise that looks like one).

    The parser uses ``re.search(r"\{.*\}", text, re.DOTALL)`` -- greedy
    with DOTALL -- so it captures from the first ``{`` to the *last* ``}``
    in the response. With two objects back-to-back (or with prose
    between them), the captured substring is not a single valid JSON
    document, so ``json.loads`` raises ``JSONDecodeError`` which the
    parser re-raises as ``AIError("bad JSON in response: ...")``.

    The Phase 2 review flagged this as a "consider hardening" item but
    explicitly asked us NOT to fix it in this pass -- only to document
    the behavior. If a future change swaps to a non-greedy or balanced-
    brace strategy, update or remove this test to match.
    """
    def handler(_request: httpx.Request) -> httpx.Response:
        return _chat_response('here you go: {"a": 1} and then {"b": 2}')

    with _client_with(handler) as client:
        with pytest.raises(AIError, match=r"bad JSON in response"):
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


# -- A3.2 / §2.6.6: per-request AI client is closed by Flask teardown -------


def test_ai_client_is_closed_at_request_teardown():
    """A3.2: when an AI-using route runs, ``_ai_client`` stores the
    ``OpenRouterClient`` on ``g`` so ``close_resources`` can call
    ``close()`` on it. After the request exits, the underlying
    ``httpx.Client`` must be closed so its connection pool is released.

    Mirrors the existing ``test_discogs_client_is_closed_at_request_teardown``
    pattern but for the AI path: install the client on ``g.ai`` inside a
    request context, then exit the context and verify the underlying
    ``httpx.Client`` was closed by the teardown hook.
    """
    from flask import g

    from lib.web import app

    def handler(_request: httpx.Request) -> httpx.Response:
        return _chat_response('{"folder": "jazz", "reason": "modal"}')

    ai_client = _client_with(handler)
    assert not ai_client._http.is_closed

    with app.test_request_context():
        g.ai = ai_client
    # Teardown has now fired; the AI client stored on g should be closed.
    assert ai_client._http.is_closed
