"""MusicBrainz API — no auth required, but UA mandatory; 1 req/sec hard limit.

Docs: https://musicbrainz.org/doc/MusicBrainz_API

ABSENCE from MusicBrainz is one of our strongest AI signals — most real artists
have an entry, most AI music projects don't. The agent should always check
MusicBrainz, even when other signals are already pointing one way.

Set `MUSICBRAINZ_USER_AGENT` env var per their policy. Implement a 1-second
floor between requests in this module.
"""

from __future__ import annotations

from typing import Any

TOOLS = [
    {
        "name": "lookup_musicbrainz",
        "description": (
            "Search MusicBrainz for an artist. Returns whether the artist has an entry, "
            "their MBID if so, relationships, and label history. ABSENCE OF AN ENTRY is "
            "itself a strong signal for AI-generated artists — record absence explicitly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"artist_name": {"type": "string"}},
            "required": ["artist_name"],
        },
    },
]


def lookup_musicbrainz(artist_name: str, **_: Any) -> dict:
    """Search MusicBrainz; return `{found: false}` cleanly on no-results."""
    raise NotImplementedError("Phase 1.")


RUNNERS = {"lookup_musicbrainz": lookup_musicbrainz}
