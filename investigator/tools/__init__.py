"""Tool registry — aggregates per-source tool schemas and runners.

Each source module under `tools/` exports:
  - `TOOLS`: list[dict]   — Claude tool schemas for that source
  - `RUNNERS`: dict[str, Callable]  — name -> implementation

This module collects them so `agent.py` can pass `TOOLS` to Claude and dispatch
through `TOOL_RUNNERS`.

`submit_verdict` is intentionally NOT in this registry — it lives in `rubric.py`
and is intercepted by the agent loop (it has no runner).
"""

from __future__ import annotations

from . import (
    deezer,
    discogs,
    genius,
    itunes,
    lastfm,
    musicbrainz,
    spotify,
    vision,
    youtube,
)

_MODULES = (itunes, musicbrainz, spotify, youtube, discogs, deezer, lastfm, genius, vision)

TOOLS: list[dict] = [t for mod in _MODULES for t in getattr(mod, "TOOLS", [])]
TOOL_RUNNERS: dict = {
    name: runner
    for mod in _MODULES
    for name, runner in getattr(mod, "RUNNERS", {}).items()
}

# Sanity: every tool schema must have a runner (except submit_verdict, which
# isn't here). Trip this at import time so a malformed scaffold fails loudly.
_schema_names = {t["name"] for t in TOOLS}
_runner_names = set(TOOL_RUNNERS)
if _schema_names != _runner_names:
    missing_runner = _schema_names - _runner_names
    missing_schema = _runner_names - _schema_names
    raise RuntimeError(
        f"tool registry mismatch: missing runners={missing_runner}, missing schemas={missing_schema}"
    )
