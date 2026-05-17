"""Shared HTTP utilities for the tools/ modules.

Every per-source tool builds requests through here so we share:
  - A consistent User-Agent identifying the project (mandatory for MusicBrainz,
    politeness for the others).
  - urllib3 retry on transient 429 / 5xx.
  - A simple rate-limit decorator for per-source minimum intervals.

Network errors propagate as exceptions; the agent loop catches them and feeds
the error back to the model as a tool_result with `is_error=true`. Empty / 404
results should be normalized to `{found: false}` by the calling tool — they're
not errors, they're answers.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_USER_AGENT = "ClAudioInvestigator/0.0.1 (+https://github.com/Meme-Theory/claudio-investigator)"


def _user_agent() -> str:
    """MusicBrainz requires a descriptive UA — env var wins so deployments can override."""
    return os.environ.get("MUSICBRAINZ_USER_AGENT") or DEFAULT_USER_AGENT


def make_session(*, retries: int = 3, backoff_factor: float = 1.0) -> requests.Session:
    """A requests.Session configured with retry on 429/5xx and a project UA."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": _user_agent(),
        "Accept": "application/json",
    })
    return session


def get_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """GET a JSON resource; raise for HTTP errors; return parsed body."""
    response = session.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def post_form(
    session: requests.Session,
    url: str,
    *,
    data: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """POST form-encoded data; raise for HTTP errors; return parsed JSON body."""
    response = session.post(url, data=data, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def rate_limited(min_interval_seconds: float) -> Callable:
    """Decorator that enforces a per-function minimum interval between calls.

    Thread-safe. Used for MusicBrainz's 1 req/sec hard limit. The interval is
    a floor — actual cadence may be slower if calls naturally space out.
    """
    lock = threading.Lock()
    state = {"last_call": 0.0}

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with lock:
                elapsed = time.monotonic() - state["last_call"]
                if elapsed < min_interval_seconds:
                    time.sleep(min_interval_seconds - elapsed)
                state["last_call"] = time.monotonic()
            return func(*args, **kwargs)

        return wrapper

    return decorator
