"""Last.fm API — generous free tier; method-based query interface.

Docs: https://www.last.fm/api

For our rubric, the rubric-relevant fields:
  - `listeners` — unique-listener count
  - `playcount` — total scrobble count
  - `playcount_per_listener` — derived. A high ratio (10+) means engaged
    fans who replay tracks; a low ratio (~1) hints at one-and-done plays
    consistent with algorithmic placement.
  - `tags` — top community tags. AI artists often have AI-related tags
    ("ai music", "suno", "generative") added by listeners who spotted it.
"""

from __future__ import annotations

import os
from typing import Any

from ._http import get_json, make_session

API_URL = "https://ws.audioscrobbler.com/2.0/"


TOOLS = [
    {
        "name": "get_lastfm_artist",
        "description": (
            "Get Last.fm artist info: listener count, scrobble count, "
            "playcount-per-listener ratio, and top community tags. The "
            "tags are notable because Last.fm listeners frequently tag "
            "AI-generated artists with markers like 'ai music' or 'suno'. "
            "Returns `{found: false}` if no entry."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"artist_name": {"type": "string"}},
            "required": ["artist_name"],
        },
    },
]


def _api_key() -> str:
    key = os.environ.get("LASTFM_API_KEY")
    if not key:
        raise RuntimeError("LASTFM_API_KEY must be set in the environment.")
    return key


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_lastfm_artist(artist_name: str, **_: Any) -> dict:
    session = make_session()
    payload = get_json(
        session,
        API_URL,
        params={
            "method": "artist.getinfo",
            "artist": artist_name,
            "api_key": _api_key(),
            "format": "json",
            "autocorrect": "1",
        },
    )

    # Last.fm returns {"error": N, "message": "..."} for not-found and other
    # error states. Per docs, error code 6 == "The artist you supplied could
    # not be found." We surface that as found=false; other codes propagate.
    if "error" in payload:
        if payload.get("error") == 6:
            return {"found": False, "query": artist_name, "reason": "not found"}
        return {
            "found": False,
            "query": artist_name,
            "error_code": payload.get("error"),
            "error_message": payload.get("message"),
        }

    artist = payload.get("artist") or {}
    if not artist:
        return {"found": False, "query": artist_name, "reason": "empty artist payload"}

    stats = artist.get("stats") or {}
    listeners = _int_or_none(stats.get("listeners"))
    playcount = _int_or_none(stats.get("playcount"))
    ratio = (playcount / listeners) if listeners and playcount else None

    tags_raw = (artist.get("tags") or {}).get("tag") or []
    if isinstance(tags_raw, dict):  # Last.fm sometimes returns a single dict
        tags_raw = [tags_raw]
    tags = [t.get("name") for t in tags_raw if t.get("name")]

    bio_summary = ((artist.get("bio") or {}).get("summary") or "").strip()

    return {
        "query": artist_name,
        "found": True,
        "name": artist.get("name"),
        "url": artist.get("url"),
        "mbid": artist.get("mbid") or None,
        "listeners": listeners,
        "playcount": playcount,
        "playcount_per_listener": round(ratio, 2) if ratio is not None else None,
        "tags": tags[:10],
        "ai_tag_present": any(
            "ai" in t.lower() or "suno" in t.lower() or "udio" in t.lower()
            for t in tags
        ),
        "bio_summary": bio_summary[:500] if bio_summary else None,
        "bio_present": bool(bio_summary),
    }


RUNNERS = {"get_lastfm_artist": get_lastfm_artist}
