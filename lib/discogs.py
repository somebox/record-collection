"""Discogs API client: auth, throttling, pagination, collection reads and writes."""

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterator

import httpx

from lib.config import USER_AGENT

API = "https://api.discogs.com"
PER_PAGE = 100
MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 10
MAX_RETRY_DELAY = 60


class DiscogsError(Exception):
    pass


class DiscogsClient:
    def __init__(self, token: str):
        self._http = httpx.Client(
            base_url=API,
            headers={
                "Authorization": f"Discogs token={token}",
                "User-Agent": USER_AGENT,
            },
            timeout=30,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.close()

    @staticmethod
    def _retry_delay(value: str | None) -> float:
        if not value:
            return DEFAULT_RETRY_DELAY
        try:
            delay = float(value)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                return DEFAULT_RETRY_DELAY
        return max(0, min(delay, MAX_RETRY_DELAY))

    def _request(self, method: str, path: str, **kwargs) -> dict:
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                raise DiscogsError(f"{method} {path}: {exc}") from exc
            if resp.status_code == 429:
                time.sleep(self._retry_delay(resp.headers.get("Retry-After")))
                continue
            if resp.is_error:
                raise DiscogsError(f"{method} {path}: HTTP {resp.status_code} {resp.text[:200]}")
            # Stay under 60 req/min: ease off as the rolling window fills up.
            remaining = int(resp.headers.get("X-Discogs-Ratelimit-Remaining", "60"))
            if remaining < 5:
                time.sleep(3)
            elif remaining < 15:
                time.sleep(1)
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()
        raise DiscogsError(f"{method} {path}: rate-limited after {MAX_RETRIES} retries")

    def _get(self, path: str, **params) -> dict:
        return self._request("GET", path, params=params or None)

    # -- reads ---------------------------------------------------------------

    def identity(self) -> dict:
        return self._get("/oauth/identity")

    def folders(self, username: str) -> list[dict]:
        return self._get(f"/users/{username}/collection/folders")["folders"]

    def fields(self, username: str) -> list[dict]:
        return self._get(f"/users/{username}/collection/fields")["fields"]

    def collection_items(self, username: str, folder_id: int = 0) -> Iterator[dict]:
        """Yield every collection instance in the folder (0 = all)."""
        page = 1
        while True:
            data = self._get(
                f"/users/{username}/collection/folders/{folder_id}/releases",
                page=page,
                per_page=PER_PAGE,
            )
            yield from data["releases"]
            if page >= data["pagination"]["pages"]:
                return
            page += 1

    def release(self, release_id: int) -> dict:
        """Full release details (community notes, lowest_price, num_for_sale)."""
        return self._get(f"/releases/{release_id}")

    # -- writes --------------------------------------------------------------

    def move_instance(
        self, username: str, folder_id: int, release_id: int, instance_id: int, to_folder_id: int
    ) -> None:
        self._request(
            "POST",
            f"/users/{username}/collection/folders/{folder_id}"
            f"/releases/{release_id}/instances/{instance_id}",
            json={"folder_id": to_folder_id},
        )

    def set_field(
        self,
        username: str,
        folder_id: int,
        release_id: int,
        instance_id: int,
        field_id: int,
        value: str,
    ) -> None:
        self._request(
            "POST",
            f"/users/{username}/collection/folders/{folder_id}"
            f"/releases/{release_id}/instances/{instance_id}/fields/{field_id}",
            json={"value": value},
        )

    def create_folder(self, username: str, name: str) -> dict:
        return self._request("POST", f"/users/{username}/collection/folders", json={"name": name})

    def rename_folder(self, username: str, folder_id: int, name: str) -> dict:
        return self._request(
            "POST", f"/users/{username}/collection/folders/{folder_id}", json={"name": name}
        )

    def delete_folder(self, username: str, folder_id: int) -> None:
        """Discogs only deletes empty folders — move the items out first."""
        self._request("DELETE", f"/users/{username}/collection/folders/{folder_id}")
