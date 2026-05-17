"""YouTube Data API v3 — 10,000 quota units/day on the free tier.

Docs: https://developers.google.com/youtube/v3

Channel age, subscriber count, and upload velocity are the signal-rich fields.
We do NOT fetch comments here (cheap astroturf target) or per-video durations
(would multiply quota cost N-fold).

Quota cost per get_youtube_channel call:
  - identifier = channel ID:    1 (channels.list) + 1 (playlistItems.list) = 2 units
  - identifier = @handle:       1 + 1 = 2 units
  - identifier = arbitrary text: 100 (search.list) + 1 + 1 = 102 units

So if the submitter provides a YouTube hint URL we extract the channel ID or
handle and stay at 2 units. Search is only the fallback. Keep an eye on this
when designing prompts — the agent should prefer ID/handle paths.
"""

from __future__ import annotations

import os
import re
from typing import Any

from ._http import get_json, make_session

API_BASE = "https://www.googleapis.com/youtube/v3"
CHANNELS_URL = f"{API_BASE}/channels"
SEARCH_URL = f"{API_BASE}/search"
PLAYLIST_ITEMS_URL = f"{API_BASE}/playlistItems"

# Recent uploads cap — playlistItems returns 50 per call; we don't paginate.
RECENT_UPLOADS_LIMIT = 50

_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_HANDLE_RE = re.compile(r"^@[A-Za-z0-9._-]+$")
_URL_CHANNEL_ID_RE = re.compile(r"(?:youtube\.com|youtu\.be)/channel/(UC[A-Za-z0-9_-]{22})")
_URL_HANDLE_RE = re.compile(r"(?:youtube\.com|youtu\.be)/(@[A-Za-z0-9._-]+)")


TOOLS = [
    {
        "name": "get_youtube_channel",
        "description": (
            "Get YouTube channel data by handle, channel ID, or arbitrary search "
            "string. Returns creation date, subscriber count, video count, and a "
            "sample of recent uploads. Channel creation date in 2024+ with high "
            "upload velocity is a strong AI signal. Prefer passing a channel ID "
            "(starts with UC) or @handle if you have one — search fallback is "
            "100x more quota-expensive."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": (
                        "Channel ID (e.g. 'UCxxx...'), @handle (e.g. '@AphexTwin'), "
                        "a youtube.com URL containing either, or a free-text artist "
                        "name (will be resolved via search)."
                    ),
                }
            },
            "required": ["identifier"],
        },
    },
]


def _api_key() -> str:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY must be set in the environment.")
    return key


def _parse_identifier(identifier: str) -> tuple[str, str]:
    """Resolve identifier to (kind, value) where kind ∈ {'id', 'handle', 'search'}."""
    stripped = identifier.strip()
    m = _URL_CHANNEL_ID_RE.search(stripped)
    if m:
        return ("id", m.group(1))
    m = _URL_HANDLE_RE.search(stripped)
    if m:
        return ("handle", m.group(1))
    if _CHANNEL_ID_RE.match(stripped):
        return ("id", stripped)
    if _HANDLE_RE.match(stripped):
        return ("handle", stripped)
    return ("search", stripped)


def _fetch_channel(session, *, channel_id=None, handle=None, key: str) -> dict | None:
    """Single channels.list call. Returns the items[0] dict or None."""
    params: dict[str, Any] = {
        "part": "snippet,statistics,contentDetails",
        "key": key,
    }
    if channel_id is not None:
        params["id"] = channel_id
    elif handle is not None:
        params["forHandle"] = handle
    else:
        raise ValueError("must pass channel_id or handle")
    payload = get_json(session, CHANNELS_URL, params=params)
    items = payload.get("items") or []
    return items[0] if items else None


def _search_for_channel(session, query: str, key: str) -> str | None:
    """search.list to find a channel ID; returns the top match's channel ID."""
    payload = get_json(
        session,
        SEARCH_URL,
        params={"part": "snippet", "q": query, "type": "channel", "maxResults": 5, "key": key},
    )
    items = payload.get("items") or []
    if not items:
        return None
    return items[0].get("id", {}).get("channelId")


def _fetch_recent_uploads(session, uploads_playlist_id: str, key: str) -> list[dict]:
    payload = get_json(
        session,
        PLAYLIST_ITEMS_URL,
        params={
            "part": "snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": RECENT_UPLOADS_LIMIT,
            "key": key,
        },
    )
    out: list[dict] = []
    for item in payload.get("items") or []:
        snippet = item.get("snippet") or {}
        out.append({
            "title": snippet.get("title"),
            "published_at": snippet.get("publishedAt"),
            "video_id": (snippet.get("resourceId") or {}).get("videoId"),
        })
    return out


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_youtube_channel(identifier: str, **_: Any) -> dict:
    """Resolve identifier → channel → recent uploads. Returns flat dict."""
    session = make_session()
    key = _api_key()

    kind, value = _parse_identifier(identifier)

    if kind == "id":
        channel = _fetch_channel(session, channel_id=value, key=key)
    elif kind == "handle":
        channel = _fetch_channel(session, handle=value, key=key)
    else:
        resolved_id = _search_for_channel(session, value, key)
        if not resolved_id:
            return {"found": False, "query": identifier, "resolved_via": "search"}
        channel = _fetch_channel(session, channel_id=resolved_id, key=key)

    if not channel:
        return {"found": False, "query": identifier, "resolved_via": kind}

    snippet = channel.get("snippet") or {}
    stats = channel.get("statistics") or {}
    content = channel.get("contentDetails") or {}

    uploads_playlist_id = (content.get("relatedPlaylists") or {}).get("uploads")
    recent_videos: list[dict] = []
    if uploads_playlist_id:
        try:
            recent_videos = _fetch_recent_uploads(session, uploads_playlist_id, key)
        except Exception:
            # Playlist fetch failures shouldn't sink the channel lookup itself.
            recent_videos = []

    publish_dates = sorted(v["published_at"] for v in recent_videos if v.get("published_at"))

    return {
        "found": True,
        "query": identifier,
        "resolved_via": kind,
        "channel_id": channel.get("id"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "country": snippet.get("country"),
        "created_at": snippet.get("publishedAt"),
        "subscriber_count": _int_or_none(stats.get("subscriberCount")),
        "subscriber_count_hidden": bool(stats.get("hiddenSubscriberCount")),
        "video_count": _int_or_none(stats.get("videoCount")),
        "view_count": _int_or_none(stats.get("viewCount")),
        "recent_uploads_sampled": len(recent_videos),
        "recent_uploads_earliest": publish_dates[0] if publish_dates else None,
        "recent_uploads_latest": publish_dates[-1] if publish_dates else None,
        "recent_uploads": recent_videos[:20],
    }


RUNNERS = {"get_youtube_channel": get_youtube_channel}
