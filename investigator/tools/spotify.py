"""Spotify Web API — client-credentials flow, 180 req/min.

Docs: https://developer.spotify.com/documentation/web-api

We expose three tools: search → artist → albums. The model is expected to
chain them when needed. Do NOT add audio-features here — that endpoint was
deprecated for new apps in Nov 2024 and is unreliable.

Auth: `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET`. The bearer token is
cached process-wide for its 1-hour lifetime so successive calls within an
investigation don't re-auth on every hop.
"""

from __future__ import annotations

import base64
import os
import threading
import time
from typing import Any

from ._http import get_json, make_session, post_form

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"

# Refresh the token if it has <60s remaining — avoids expiry-mid-request.
_REFRESH_MARGIN_SECONDS = 60

_token_lock = threading.Lock()
_token_state: dict[str, Any] = {"access_token": None, "expires_at": 0.0, "client_id": None}


TOOLS = [
    {
        "name": "search_spotify_artist",
        "description": (
            "Search Spotify for an artist by name. Returns top matches with their "
            "Spotify IDs, follower counts, popularity scores, and genres. Use this "
            "first to resolve an artist name to a Spotify ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "artist_name": {"type": "string"},
                "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
            "required": ["artist_name"],
        },
    },
    {
        "name": "get_spotify_artist",
        "description": (
            "Get Spotify artist profile by Spotify ID. Returns popularity (0-100), "
            "follower count, genres, and image URL. The popularity-to-followers ratio "
            "is a key AI signal (high popularity, low followers → suspicious)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"spotify_id": {"type": "string"}},
            "required": ["spotify_id"],
        },
    },
    {
        "name": "get_spotify_albums",
        "description": (
            "Get all albums and singles by a Spotify artist. Returns release dates, "
            "types, and track counts. Used for release-velocity analysis — high output "
            "with no pre-2024 catalog is a major AI signal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "spotify_id": {"type": "string"},
                "include_groups": {
                    "type": "string",
                    "default": "album,single",
                    "description": "Comma-separated subset of: album, single, appears_on, compilation",
                },
            },
            "required": ["spotify_id"],
        },
    },
]


# --- Auth -------------------------------------------------------------------


def _get_access_token() -> str:
    """Return a valid bearer token; refresh via client-credentials if needed."""
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in the environment."
        )

    with _token_lock:
        cached = _token_state.get("access_token")
        expires_at = _token_state.get("expires_at") or 0.0
        cached_client_id = _token_state.get("client_id")
        if (
            cached
            and cached_client_id == client_id
            and (expires_at - time.monotonic()) > _REFRESH_MARGIN_SECONDS
        ):
            return cached

        auth_b64 = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        session = make_session()
        payload = post_form(
            session,
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            headers={
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        _token_state["access_token"] = access_token
        _token_state["expires_at"] = time.monotonic() + expires_in
        _token_state["client_id"] = client_id
        return access_token


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_access_token()}"}


# --- Tools ------------------------------------------------------------------


def _normalize_artist(entry: dict) -> dict:
    images = entry.get("images") or []
    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "popularity": entry.get("popularity"),
        "followers_count": (entry.get("followers") or {}).get("total"),
        "genres": entry.get("genres") or [],
        "image_url": images[0]["url"] if images else None,
        "external_url": (entry.get("external_urls") or {}).get("spotify"),
    }


def _normalize_album(entry: dict) -> dict:
    images = entry.get("images") or []
    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "album_type": entry.get("album_type"),
        "album_group": entry.get("album_group"),
        "release_date": entry.get("release_date"),
        "release_date_precision": entry.get("release_date_precision"),
        "total_tracks": entry.get("total_tracks"),
        "artwork_url": images[0]["url"] if images else None,
        "external_url": (entry.get("external_urls") or {}).get("spotify"),
    }


def search_spotify_artist(artist_name: str, limit: int = 5, **_: Any) -> dict:
    session = make_session()
    payload = get_json(
        session,
        f"{API_BASE}/search",
        params={"q": artist_name, "type": "artist", "limit": limit},
        headers=_auth_headers(),
    )
    items = (payload.get("artists") or {}).get("items") or []
    candidates = [_normalize_artist(a) for a in items]
    query_normalized = artist_name.strip().casefold()
    exact = [c for c in candidates if (c.get("name") or "").strip().casefold() == query_normalized]
    return {
        "query": artist_name,
        "found": bool(candidates),
        "found_exact": bool(exact),
        "total_count": (payload.get("artists") or {}).get("total", len(candidates)),
        "candidates": candidates,
        "exact_match": exact[0] if exact else None,
    }


def get_spotify_artist(spotify_id: str, **_: Any) -> dict:
    session = make_session()
    payload = get_json(
        session,
        f"{API_BASE}/artists/{spotify_id}",
        headers=_auth_headers(),
    )
    return _normalize_artist(payload)


def get_spotify_albums(spotify_id: str, include_groups: str = "album,single", **_: Any) -> dict:
    session = make_session()
    payload = get_json(
        session,
        f"{API_BASE}/artists/{spotify_id}/albums",
        params={"include_groups": include_groups, "limit": 50},
        headers=_auth_headers(),
    )
    items = payload.get("items") or []
    albums = [_normalize_album(a) for a in items]
    release_dates = sorted(a["release_date"] for a in albums if a.get("release_date"))
    return {
        "spotify_id": spotify_id,
        "album_count": len(albums),
        "albums": albums,
        "earliest_release_date": release_dates[0] if release_dates else None,
        "latest_release_date": release_dates[-1] if release_dates else None,
    }


def _reset_token_cache_for_testing() -> None:
    """Test-only hook; the agent loop never calls this."""
    with _token_lock:
        _token_state["access_token"] = None
        _token_state["expires_at"] = 0.0
        _token_state["client_id"] = None


RUNNERS = {
    "search_spotify_artist": search_spotify_artist,
    "get_spotify_artist": get_spotify_artist,
    "get_spotify_albums": get_spotify_albums,
}
