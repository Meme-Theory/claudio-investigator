"""Last.fm API — generous free tier.

Docs: https://www.last.fm/api

The shape of an artist's listener-count growth curve is signal-rich. AI
projects often have step-function listener histories (zero → many overnight
on a playlist placement), while real artists have organic growth curves.
"""

from __future__ import annotations

from typing import Any

TOOLS = [
    {
        "name": "get_lastfm_artist",
        "description": (
            "Get Last.fm artist info: listener count, scrobble count, top tags, and "
            "bio. The scrobble-to-listener ratio and bio quality are useful signals. "
            "Returns `{found: false}` if no entry."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"artist_name": {"type": "string"}},
            "required": ["artist_name"],
        },
    },
]


def get_lastfm_artist(artist_name: str, **_: Any) -> dict:
    raise NotImplementedError("Phase 2.")


RUNNERS = {"get_lastfm_artist": get_lastfm_artist}
