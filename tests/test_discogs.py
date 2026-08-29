from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from lib.discogs import DEFAULT_RETRY_DELAY, DiscogsClient, DiscogsError


def client_with(handler):
    client = DiscogsClient("token")
    client.close()
    client._http = httpx.Client(
        base_url="https://api.discogs.com",
        transport=httpx.MockTransport(handler),
    )
    return client


def test_transport_errors_become_discogs_errors():
    def offline(request):
        raise httpx.ConnectError("offline", request=request)

    with client_with(offline) as client:
        with pytest.raises(DiscogsError, match=r"GET /oauth/identity: offline") as exc:
            client.identity()
    assert isinstance(exc.value.__cause__, httpx.ConnectError)


def test_retry_after_http_date_is_bounded(monkeypatch):
    responses = iter(
        [
            httpx.Response(
                429,
                headers={
                    "Retry-After": format_datetime(
                        datetime.now(timezone.utc) + timedelta(minutes=5), usegmt=True
                    )
                },
            ),
            httpx.Response(200, json={"username": "tester"}),
        ]
    )
    waits = []
    monkeypatch.setattr("lib.discogs.time.sleep", waits.append)

    with client_with(lambda _request: next(responses)) as client:
        assert client.identity() == {"username": "tester"}
    assert waits == [60]


def test_invalid_retry_after_uses_default(monkeypatch):
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "eventually"}),
            httpx.Response(200, json={"username": "tester"}),
        ]
    )
    waits = []
    monkeypatch.setattr("lib.discogs.time.sleep", waits.append)

    with client_with(lambda _request: next(responses)) as client:
        assert client.identity() == {"username": "tester"}
    assert waits == [DEFAULT_RETRY_DELAY]
