"""iTunes Search API — no auth, generous unenforced limits.

Docs: https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/

Used as the first cheap broad-coverage call: confirms an artist exists in the
Apple catalog and pulls release dates, album list, artwork URLs, country, and
genre in one shot.
"""

from __future__ import annotations

from typing import Any

TOOLS = [
    {
        "name": "lookup_itunes",
        "description": (
            "Search iTunes for an artist. Returns artist metadata including release "
            "dates, album list, artwork URLs, and country. Use this as the first cheap "
            "broad-coverage call for any artist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "artist_name": {"type": "string"},
                "country": {"type": "string", "default": "us"},
            },
            "required": ["artist_name"],
        },
    },
]


def lookup_itunes(artist_name: str, country: str = "us", **_: Any) -> dict:
    """Search iTunes and normalize the response into a flat dict."""
    raise NotImplementedError("Phase 1.")


RUNNERS = {"lookup_itunes": lookup_itunes}
