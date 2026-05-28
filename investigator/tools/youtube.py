"""YouTube Data API v3 — 10,000 quota units/day on the free tier.

Docs: https://developers.google.com/youtube/v3

Channel age, subscriber count, upload velocity, and recent-video durations
are the signal-rich fields. We do NOT fetch comments here (cheap astroturf
target).

Quota cost per get_youtube_channel call:
  - identifier = channel ID:    1 (channels.list) + 1 (playlistItems.list) + 1 (videos.list batch) = 3 units
  - identifier = @handle:       1 + 1 + 1 = 3 units
  - identifier = arbitrary text: 100 (search.list) + 1 + 1 + 1 = 103 units

So if the submitter provides a YouTube hint URL we extract the channel ID or
handle and stay at 3 units. Search is only the fallback. videos.list is
batched 50-at-a-time so the duration fetch is one call regardless of how
many recent uploads we sampled.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from ._http import get_json, make_session

API_BASE = "https://www.googleapis.com/youtube/v3"
CHANNELS_URL = f"{API_BASE}/channels"
SEARCH_URL = f"{API_BASE}/search"
PLAYLIST_ITEMS_URL = f"{API_BASE}/playlistItems"
VIDEOS_URL = f"{API_BASE}/videos"

# Recent uploads cap — playlistItems returns 50 per call; we don't paginate.
RECENT_UPLOADS_LIMIT = 50

# ISO 8601 duration parser — YouTube returns durations like "PT3M42S",
# "PT1H2M3S", "PT45S". The format is restricted enough that a focused regex
# beats reaching for `isodate` / `pendulum` here.
_ISO_DURATION_RE = re.compile(
    r"^PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?$"
)


def _parse_iso_duration(value: str | None) -> int | None:
    """ISO 8601 duration → seconds. Returns None on malformed input."""
    if not value:
        return None
    m = _ISO_DURATION_RE.match(value)
    if not m:
        return None
    h = int(m.group("h") or 0)
    m_ = int(m.group("m") or 0)
    s = int(m.group("s") or 0)
    return h * 3600 + m_ * 60 + s

_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_HANDLE_RE = re.compile(r"^@[A-Za-z0-9._-]+$")
# Channel/handle URLs from any YouTube host (desktop, music, mobile, short).
_HOST = r"(?:music\.|www\.|m\.)?youtu(?:be\.com|\.be)"
_URL_CHANNEL_ID_RE = re.compile(rf"{_HOST}/channel/(UC[A-Za-z0-9_-]{{22}})")
_URL_HANDLE_RE = re.compile(rf"{_HOST}/(@[A-Za-z0-9._-]+)")


def _extract_video_id(s: str) -> str | None:
    """Pull a YouTube video ID out of a watch / share / short / embed URL.

    Uses urlparse instead of a regex because share URLs vary: desktop
    youtube.com/watch?v=ID&t=..., music.youtube.com/watch?v=ID&si=...,
    youtu.be/ID, /shorts/ID, /embed/ID. Query-param `v=` covers the
    /watch family across all hosts; the path-suffix forms are explicit.
    Returns None for non-video inputs (channel URLs, handles, bare names).
    """
    try:
        parsed = urlparse(s.strip())
    except Exception:
        return None
    if not parsed.scheme and not parsed.netloc:
        return None
    if parsed.query:
        v = parse_qs(parsed.query).get("v")
        if v and len(v[0]) == 11:
            return v[0]
    parts = [p for p in parsed.path.split("/") if p]
    if parsed.netloc.endswith("youtu.be") and parts and len(parts[0]) == 11:
        return parts[0]
    if len(parts) == 2 and parts[0] in ("shorts", "embed", "v") and len(parts[1]) == 11:
        return parts[1]
    return None


TOOLS = [
    {
        "name": "get_youtube_channel",
        "description": (
            "Get YouTube channel data by handle, channel ID, watch URL, or "
            "arbitrary search string. Returns creation date, subscriber count, "
            "video count, and a sample of recent uploads WITH per-video durations "
            "in seconds. When given a watch/share URL (e.g. "
            "music.youtube.com/watch?v=ID), the tool resolves video → channel "
            "automatically and surfaces the URL-anchored video's snippet as "
            "`anchor_video` (title, description, publishedAt, channel title). "
            "ALWAYS pass the submitter's youtube_url hint directly to this tool "
            "— do NOT fall back to searching by artist name. The watch URL is "
            "the authoritative anchor; name search returns the wrong artist in "
            "every same-name-collision case. Channel creation date in 2024+ "
            "with high upload velocity is a strong AI signal. Recent-uploads "
            "durations feed the `suno-duration-cap` marker as a secondary source "
            "to Deezer. Recent-uploads titles often contain explicit AI markers "
            "(\"[AI]\", \"(AI)\", \"Suno\", etc.) — read them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": (
                        "Channel ID (e.g. 'UCxxx...'), @handle (e.g. '@AphexTwin'), "
                        "a youtube.com or music.youtube.com URL (watch/share/channel/"
                        "handle), or a free-text artist name (search; quota-expensive "
                        "fallback only)."
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
    """Resolve identifier to (kind, value) where kind ∈ {'id', 'handle', 'video', 'search'}."""
    stripped = identifier.strip()
    m = _URL_CHANNEL_ID_RE.search(stripped)
    if m:
        return ("id", m.group(1))
    m = _URL_HANDLE_RE.search(stripped)
    if m:
        return ("handle", m.group(1))
    # Watch / share / short URL — the submitter's primary anchor.
    video_id = _extract_video_id(stripped)
    if video_id:
        return ("video", video_id)
    if _CHANNEL_ID_RE.match(stripped):
        return ("id", stripped)
    if _HANDLE_RE.match(stripped):
        return ("handle", stripped)
    return ("search", stripped)


def _resolve_video_to_channel(session, video_id: str, key: str) -> dict | None:
    """videos.list → channelId + video snippet. 1 quota unit.

    Returns {'channel_id', 'video': {...snippet...}} so the caller can both
    anchor on the right channel AND surface the URL-anchored video's specific
    details (title, description with distributor credits, publish date) to
    the agent. That second piece is what enables sub-catalog isolation —
    without the video's description the agent can't filter the channel's
    uploads to the URL-anchored sub-catalog.
    """
    payload = get_json(
        session,
        VIDEOS_URL,
        params={"part": "snippet", "id": video_id, "key": key},
    )
    items = payload.get("items") or []
    if not items:
        return None
    snippet = items[0].get("snippet") or {}
    channel_id = snippet.get("channelId")
    if not channel_id:
        return None
    return {
        "channel_id": channel_id,
        "video": {
            "video_id": video_id,
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "published_at": snippet.get("publishedAt"),
            "channel_title": snippet.get("channelTitle"),
        },
    }


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


def _fetch_video_durations(session, video_ids: list[str], key: str) -> dict[str, int | None]:
    """One videos.list call returns contentDetails for up to 50 IDs.

    Best-effort — returns empty mapping on API failure so the caller can
    proceed without durations rather than failing the whole channel lookup.
    The duration signal feeds `suno-duration-cap` but isn't load-bearing for
    presence/velocity, which use other fields.
    """
    if not video_ids:
        return {}
    try:
        payload = get_json(
            session,
            VIDEOS_URL,
            params={
                "part": "contentDetails",
                "id": ",".join(video_ids[:50]),
                "key": key,
            },
        )
    except Exception:
        return {}
    out: dict[str, int | None] = {}
    for item in payload.get("items") or []:
        vid = item.get("id")
        iso = (item.get("contentDetails") or {}).get("duration")
        if vid:
            out[vid] = _parse_iso_duration(iso)
    return out


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_youtube_channel(identifier: str, **_: Any) -> dict:
    """Resolve identifier → channel → recent uploads. Returns flat dict.

    When `identifier` is a watch URL (the submitter's typical share link),
    we resolve video → channel via videos.list (+1 quota unit) and surface
    the URL-anchored video's snippet on the result as `anchor_video`. The
    agent needs the video's description to identify the distributor and
    release window of the URL-anchored sub-catalog for RULE A scoping.
    """
    session = make_session()
    key = _api_key()

    kind, value = _parse_identifier(identifier)
    anchor_video: dict | None = None

    if kind == "id":
        channel = _fetch_channel(session, channel_id=value, key=key)
    elif kind == "handle":
        channel = _fetch_channel(session, handle=value, key=key)
    elif kind == "video":
        resolved = _resolve_video_to_channel(session, value, key)
        if not resolved:
            return {"found": False, "query": identifier, "resolved_via": "video"}
        anchor_video = resolved["video"]
        channel = _fetch_channel(session, channel_id=resolved["channel_id"], key=key)
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

    # Annotate recent videos with audio duration. One batched videos.list call
    # is enough for the 20 we sample. Lyric videos / music videos may add a
    # few seconds vs. the audio-only equivalent — see `suno-duration-cap`
    # marker definition for how this signal is interpreted.
    sample = recent_videos[:20]
    video_ids = [v["video_id"] for v in sample if v.get("video_id")]
    duration_map = _fetch_video_durations(session, video_ids, key)
    for v in sample:
        v["duration_seconds"] = duration_map.get(v.get("video_id"))

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
        "recent_uploads": sample,
        "anchor_video": anchor_video,
    }


RUNNERS = {"get_youtube_channel": get_youtube_channel}
