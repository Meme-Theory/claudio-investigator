"""Shared pytest fixtures.

Conventions:
  - HTTP is mocked at the `requests` boundary using the `responses` library.
    Don't mock our own tool functions — exercise the real parsing code with
    canned API responses from `tests/fixtures/`.
  - One fixture per data source (`itunes_response`, `musicbrainz_response`, ...)
    loads the corresponding JSON from `tests/fixtures/`.
  - For agent-loop tests, mock the `anthropic.Anthropic` client at the SDK
    boundary — pass synthetic `Message` objects, don't hit the API.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE_DIR


def load_fixture(name: str) -> dict:
    """Read a JSON fixture file. Used by per-source fixtures below."""
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def itunes_known_ai_response() -> dict:
    """Canned iTunes response for a known AI-generated artist (Phase 1 fixture)."""
    return load_fixture("itunes_known_ai.json")


@pytest.fixture
def itunes_known_human_response() -> dict:
    """Canned iTunes response for a known human artist (Phase 1 fixture)."""
    return load_fixture("itunes_known_human.json")
