"""Discogs API — free token, 60 req/min anon, 240/min auth.

Docs: https://www.discogs.com/developers

Physical release presence is a strong HUMAN signal — AI music projects rarely
press vinyl or CD. Absence of Discogs entries (especially for an artist with
significant streaming presence) is a strong AI signal.
"""

from __future__ import annotations

from typing import Any

TOOLS = [
    {
        "name": "lookup_discogs",
        "description": (
            "Search Discogs for an artist. Returns presence in the catalog, label "
            "history, and any physical release info (vinyl, CD, tape). PHYSICAL "
            "RELEASES are a strong human signal; their absence on a prolific streaming "
            "artist is a strong AI signal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"artist_name": {"type": "string"}},
            "required": ["artist_name"],
        },
    },
]


def lookup_discogs(artist_name: str, **_: Any) -> dict:
    raise NotImplementedError("Phase 2.")


RUNNERS = {"lookup_discogs": lookup_discogs}
