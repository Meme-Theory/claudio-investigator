"""Genius API — free token, generous limits.

Docs: https://docs.genius.com/

We use this for lyric retrieval so the agent can run text-pattern analysis
internally (GPT rhyme dependencies, semantic loops, generic-template phrasing).
The agent does the pattern detection — this tool just fetches text.
"""

from __future__ import annotations

from typing import Any

TOOLS = [
    {
        "name": "get_genius_lyrics",
        "description": (
            "Fetch lyrics for an artist's tracks from Genius. Returns lyrics text "
            "for up to N tracks. Useful for detecting GPT-style lyric patterns. The "
            "model should analyze the returned text itself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "artist_name": {"type": "string"},
                "max_tracks": {"type": "integer", "default": 3, "minimum": 1, "maximum": 10},
            },
            "required": ["artist_name"],
        },
    },
]


def get_genius_lyrics(artist_name: str, max_tracks: int = 3, **_: Any) -> dict:
    raise NotImplementedError("Phase 2.")


RUNNERS = {"get_genius_lyrics": get_genius_lyrics}
