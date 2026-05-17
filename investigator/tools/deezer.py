"""Deezer Public API — no auth, ~50 req per 5 seconds.

Docs: https://developers.deezer.com/api

Used mainly as a cross-platform existence check and fan count source.
"""

from __future__ import annotations

from typing import Any

TOOLS = [
    {
        "name": "lookup_deezer",
        "description": (
            "Search Deezer for an artist. Returns existence, fan count, album coverage, "
            "and Deezer ID. Used as a cross-platform presence check."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"artist_name": {"type": "string"}},
            "required": ["artist_name"],
        },
    },
]


def lookup_deezer(artist_name: str, **_: Any) -> dict:
    raise NotImplementedError("Phase 2.")


RUNNERS = {"lookup_deezer": lookup_deezer}
