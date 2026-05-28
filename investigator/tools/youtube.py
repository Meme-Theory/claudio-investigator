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
            "Get YouTube channel data by channel ID, @handle, or watch URL. "
            "Returns creation date, subscriber count, video count, and a sample "
            "of recent uploads WITH per-video durations in seconds. When given "
            "a watch/share URL (music.youtube.com/watch?v=ID), the tool resolves "
            "video → channel automatically and surfaces the URL-anchored "
            "video's snippet as `anchor_video`. ONLY pass the submitter's "
            "youtube_url hint to this tool. Free-text artist names are "
            "REJECTED — name search returns the wrong artist in every same-"
            "name-collision case and is the laundering attack surface. "
            "If no YouTube URL was provided by the submitter, do not call this "
            "tool; skip the YouTube evaluation and rely on iTunes / MB / "
            "Deezer name lookups instead. Channel creation date in 2024+ with "
            "high upload velocity is a strong AI signal. Recent-uploads "
            "durations feed `suno-duration-cap` as a secondary source to "
            "Deezer. Recent-uploads titles often contain explicit AI markers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": (
                        "MUST be one of: a channel ID (UCxxx...), @handle, or "
                        "a youtube.com / music.youtube.com URL (watch / share / "
                        "channel / handle). Free-text artist names are rejected."
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


# "Provided to YouTube by <DISTRIBUTOR>" is the canonical first line of
# auto-generated Topic-channel video descriptions. Pulling it out per-upload
# lets the agent see: which distributor delivered each track, whether the
# whole channel comes from one distributor (squatter signature) or several
# (real artist whose label has digital + sync deals across services), and
# whether the ℗ copyright line names a real label vs. self-publishing.
_PROVIDED_BY_RE = re.compile(r"Provided to YouTube by\s+(.+?)$", re.MULTILINE)
_PCOPY_RE = re.compile(r"℗\s*(?:\d{4}\s+)?(.+?)$", re.MULTILINE)


def _parse_video_meta(description: str | None) -> dict:
    """Extract distributor + ℗ copyright line from a Topic-channel description."""
    if not description:
        return {"distributor": None, "copyright": None}
    dist_m = _PROVIDED_BY_RE.search(description)
    cpy_m = _PCOPY_RE.search(description)
    return {
        "distributor": dist_m.group(1).strip() if dist_m else None,
        "copyright": cpy_m.group(1).strip() if cpy_m else None,
    }


def _fetch_video_details(session, video_ids: list[str], key: str) -> dict[str, dict]:
    """One videos.list call returns contentDetails + snippet for up to 50 IDs.

    Best-effort — returns empty mapping on API failure so the caller can
    proceed without per-video details rather than failing the whole channel
    lookup. Snippet costs nothing extra on the same call (videos.list bills
    per call, not per part).

    Returns: {video_id: {duration_seconds, description, published_at, distributor, copyright}}
    """
    if not video_ids:
        return {}
    try:
        payload = get_json(
            session,
            VIDEOS_URL,
            params={
                "part": "contentDetails,snippet",
                "id": ",".join(video_ids[:50]),
                "key": key,
            },
        )
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for item in payload.get("items") or []:
        vid = item.get("id")
        if not vid:
            continue
        iso = (item.get("contentDetails") or {}).get("duration")
        snip = item.get("snippet") or {}
        desc = snip.get("description")
        meta = _parse_video_meta(desc)
        out[vid] = {
            "duration_seconds": _parse_iso_duration(iso),
            "description": desc,
            "published_at": snip.get("publishedAt"),
            "distributor": meta["distributor"],
            "copyright": meta["copyright"],
        }
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
        # Name-search is REMOVED — the agent must use a URL / channel ID /
        # handle from the submitter's youtube_url hint. Googling the artist
        # name returns the wrong artist in every same-name-collision case
        # and gives the agent a fake anchor it can pretend is the URL the
        # submitter sent. If no submitter URL is available, no YouTube
        # evaluation — fall back to iTunes / MB / Deezer name lookups
        # (those return DSP metadata, not navigable URLs to a wrong
        # artist's personal channel).
        return {
            "found": False,
            "query": identifier,
            "resolved_via": "search-refused",
            "error": (
                "get_youtube_channel does not accept free-text artist names. "
                "Pass the submitter's youtube_url hint, a channel ID "
                "(UCxxx...), an @handle, or a watch/share URL. If no "
                "YouTube URL was provided by the submitter, skip the "
                "YouTube evaluation — do not name-search."
            ),
        }

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

    # Annotate recent videos with duration + description-derived metadata
    # (distributor name from "Provided to YouTube by ..." line, ℗ copyright
    # holder). One batched videos.list call is enough for the 20 we sample;
    # adding the snippet part doesn't increase quota cost.
    sample = recent_videos[:20]
    video_ids = [v["video_id"] for v in sample if v.get("video_id")]
    details_map = _fetch_video_details(session, video_ids, key)
    for v in sample:
        d = details_map.get(v.get("video_id"), {})
        v["duration_seconds"] = d.get("duration_seconds")
        v["distributor"] = d.get("distributor")
        v["copyright"] = d.get("copyright")

    publish_dates = sorted(v["published_at"] for v in recent_videos if v.get("published_at"))

    # Batch-dump / single-distributor signature aggregates. AI squatters
    # routinely deliver an entire fake catalog through one distributor in a
    # single upload day; real artists' catalogs are spread across release
    # windows and (often) multiple distributors over their career. Surface
    # these aggregates so the agent doesn't have to recompute them from the
    # raw recent_uploads list.
    distributors = [v.get("distributor") for v in sample if v.get("distributor")]
    distributor_counts: dict[str, int] = {}
    for d in distributors:
        distributor_counts[d] = distributor_counts.get(d, 0) + 1
    dominant_distributor = max(distributor_counts, key=distributor_counts.get) if distributor_counts else None
    distributor_concentration = (
        distributor_counts[dominant_distributor] / len(distributors)
        if dominant_distributor and distributors else 0.0
    )

    upload_day_set = {
        (v.get("published_at") or "")[:10] for v in sample if v.get("published_at")
    }
    upload_day_set.discard("")

    copyrights = [v.get("copyright") for v in sample if v.get("copyright")]
    copyright_counts: dict[str, int] = {}
    for c in copyrights:
        copyright_counts[c] = copyright_counts.get(c, 0) + 1
    dominant_copyright = max(copyright_counts, key=copyright_counts.get) if copyright_counts else None

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
        # Squatter-pattern aggregates (see SIGNAL_MARKERS::single-batch-dump).
        "distributor_counts": distributor_counts,
        "dominant_distributor": dominant_distributor,
        "distributor_concentration": round(distributor_concentration, 2),
        "unique_upload_days": len(upload_day_set),
        "dominant_copyright": dominant_copyright,
    }


RUNNERS = {"get_youtube_channel": get_youtube_channel}
