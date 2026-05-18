"""Shared pytest fixtures.

Conventions:
  - HTTP is mocked at the `requests` boundary using the `responses` library.
    Don't mock our own tool functions — exercise the real parsing code with
    canned API responses from `tests/fixtures/`.
  - For agent-loop tests, mock the `anthropic.Anthropic` client at the SDK
    boundary — pass synthetic `Message` objects, don't hit the API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture
def load_fixture():
    """Return a loader that reads JSON fixtures by filename."""

    def _load(name: str) -> Any:
        return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))

    return _load


