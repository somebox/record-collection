"""OpenRouter client. The model alias includes the tilde; it currently resolves
to a Gemini Flash reasoning model, so give it token headroom and low effort."""

import json
import re

import httpx

from lib.config import OPENROUTER_MODEL

API = "https://openrouter.ai/api/v1"


class AIError(Exception):
    pass


class OpenRouterClient:
    def __init__(self, key: str, model: str = OPENROUTER_MODEL):
        self.model = model
        self._http = httpx.Client(
            base_url=API,
            headers={"Authorization": f"Bearer {key}"},
            timeout=120,
        )

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2000,
        web_search: bool = False,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.model + (":online" if web_search else ""),
            "messages": messages,
            "max_tokens": max_tokens,
            "reasoning": {"effort": "low"},
        }
        resp = self._http.post("/chat/completions", json=payload)
        if resp.is_error:
            raise AIError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        choice = data["choices"][0]
        content = choice["message"].get("content")
        if not content:
            raise AIError(f"empty response (finish_reason={choice.get('finish_reason')})")
        return content.strip()

    def complete_json(self, prompt: str, system: str | None = None, **kwargs) -> dict:
        text = self.complete(prompt, system=system, **kwargs)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise AIError(f"no JSON in response: {text[:200]}")
        try:
            return json.loads(match.group())
        except json.JSONDecodeError as e:
            raise AIError(f"bad JSON in response: {e}") from e


SUMMARIZE_SYSTEM = """You write tiny printed labels for vinyl record sleeves.
Given album metadata (and possibly the Discogs release notes), reply with JSON only:
{"style": "...", "summary": "..."}
- style: 3-5 short lowercase descriptors of mood and sound, comma-separated,
  e.g. "ambient, quiet, electronic, minimalist" or "upbeat, catchy vocals, goth flavor".
- summary: one or two plain sentences, max 220 characters total, that say what the
  album is and why it matters. Concrete, no marketing fluff, no "this album"."""

CLASSIFY_SYSTEM = """You file vinyl records into the folders of a personal collection.
Reply with JSON only: {"folder": "<exact folder name from the list, or none>", "reason": "<short>"}"""


def item_context(item: dict, release_notes: str | None = None) -> str:
    parts = [
        f"Title: {item['title']}",
        f"Artist: {item['artist']}",
        f"Year: {item['year'] or 'unknown'}",
        f"Genres: {item['genres'] or '-'}",
        f"Discogs styles: {item['discogs_styles'] or '-'}",
    ]
    if release_notes:
        parts.append(f"Discogs release notes: {release_notes[:1500]}")
    return "\n".join(parts)


def summarize_item(
    client: OpenRouterClient, item: dict, release_notes: str | None = None
) -> dict:
    """Draft {"style", "summary"} for an item; searches the web when Discogs
    has no release notes to work from."""
    draft = client.complete_json(
        item_context(item, release_notes),
        system=SUMMARIZE_SYSTEM,
        web_search=not release_notes,
    )
    if not draft.get("style") or not draft.get("summary"):
        raise AIError(f"incomplete draft: {draft}")
    return {"style": str(draft["style"]).strip(), "summary": str(draft["summary"]).strip()}


def classify_item(client: OpenRouterClient, item: dict, folder_names: list[str]) -> dict:
    prompt = (
        f"Folders: {', '.join(folder_names)}\n\n{item_context(item)}\n\n"
        "Which folder fits this record best?"
    )
    return client.complete_json(prompt, system=CLASSIFY_SYSTEM)
