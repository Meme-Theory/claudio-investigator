"""Spotify Web API — client-credentials flow, 180 req/min.

Docs: https://developer.spotify.com/documentation/web-api

We expose three tools: search → artist → albums. The model is expected to
chain them when needed. Do NOT add audio-features here — that endpoint was
deprecated for new apps in Nov 2024 and is unreliable.

Auth: `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET`. Cache the bearer token
across calls within an investigation; tokens last 1 hour.
"""

from __future__ import annotations

from typing import Any

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


def search_spotify_artist(artist_name: str, limit: int = 5, **_: Any) -> dict:
    raise NotImplementedError("Phase 1.")


def get_spotify_artist(spotify_id: str, **_: Any) -> dict:
    raise NotImplementedError("Phase 1.")


def get_spotify_albums(spotify_id: str, include_groups: str = "album,single", **_: Any) -> dict:
    raise NotImplementedError("Phase 1.")


RUNNERS = {
    "search_spotify_artist": search_spotify_artist,
    "get_spotify_artist": get_spotify_artist,
    "get_spotify_albums": get_spotify_albums,
}
