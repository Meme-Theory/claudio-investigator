"""YouTube Data API v3 — 10,000 units/day on the free tier.

Docs: https://developers.google.com/youtube/v3

Channel age, subscriber count, and upload velocity are the signal-rich fields.
Comments are a sample-only source — pull a small page if needed but don't
build core signals on them (they're easily astroturfed).

Budget note: search.list costs 100 units; channels.list costs 1 unit. Resolve
identifiers cheaply and only burn search quota when necessary.
"""

from __future__ import annotations

from typing import Any

TOOLS = [
    {
        "name": "get_youtube_channel",
        "description": (
            "Get YouTube channel data by handle, custom URL, or channel ID. Returns "
            "creation date, subscriber count, video count, and recent upload velocity. "
            "Channel creation date in 2024+ with high upload velocity is a strong "
            "AI signal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "Channel ID, @handle, or custom URL slug.",
                }
            },
            "required": ["identifier"],
        },
    },
]


def get_youtube_channel(identifier: str, **_: Any) -> dict:
    raise NotImplementedError("Phase 2.")


RUNNERS = {"get_youtube_channel": get_youtube_channel}
