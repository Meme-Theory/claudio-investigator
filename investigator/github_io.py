"""GitHub I/O: parse the issue body, post the verdict comment, open the PR.

Used by `investigate-from-issue` running inside `.github/workflows/investigate.yml`.
Auth is via `GH_TOKEN` (the workflow-supplied GITHUB_TOKEN). Repo is `GH_REPO`.

We use the `gh` CLI rather than the REST API directly — the runner has it
pre-installed and authenticated, and shelling out keeps this module small.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .schema import ArtistRecord, Verdict

logger = logging.getLogger(__name__)


@dataclass
class IssueSubmission:
    """Parsed contents of an `investigate` issue body."""

    issue_number: int
    artist_name: str
    spotify_url: str | None = None
    youtube_url: str | None = None
    apple_url: str | None = None
    submitter_notes: str | None = None


def parse_issue_body(body: str, issue_number: int) -> IssueSubmission:
    """Pull structured fields out of the markdown the issue template renders.

    The template (`.github/ISSUE_TEMPLATE/investigate.yml`) writes labelled
    sections in a stable order. We match on the section heading rather than
    field position so a re-ordered template doesn't silently break parsing.
    """
    raise NotImplementedError("Phase 3.")


def comment_on_issue(issue_number: int, verdict: Verdict, budget_summary: dict) -> None:
    """Post the evidence-trail comment on the originating issue.

    Markdown structure:
      ## Verdict: <label> (confidence <0.xx>)
      ### Markers
      - marker-1
      ### Evidence
      - **source** — finding (weight)
      ### Reasoning
      <paragraph>
      ---
      <budget summary footer>
    """
    raise NotImplementedError("Phase 3.")


def open_record_pr(record: ArtistRecord, issue_number: int) -> str:
    """Create a branch, write src/{slug}.json, commit, open PR. Return PR URL.

    Only call when confidence ≥ AUTO_MERGE_THRESHOLD (default 0.90).
    Branch naming: `investigate/{slug}`.
    PR body links back to the originating issue.
    """
    raise NotImplementedError("Phase 3.")


def apply_label(issue_number: int, label: str) -> None:
    """Apply one of: 'needs-review', 'low-confidence', 'auto-merged'."""
    raise NotImplementedError("Phase 3.")


# --- Slug derivation --------------------------------------------------------

_SLUG_NON_ALPHA = re.compile(r"[^a-z0-9]+")


def _normalize(s: str) -> str:
    """Lowercase, ASCII, non-alphanumerics collapsed to single hyphens, trimmed."""
    ascii_s = s.lower().encode("ascii", "ignore").decode("ascii")
    return _SLUG_NON_ALPHA.sub("-", ascii_s).strip("-")


def slug_for(
    artist_name: str,
    *,
    existing_slugs: set[str] | None = None,
    genre: str | None = None,
    country_code: str | None = None,
) -> str:
    """Produce a stable slug for `src/{slug}.json`.

    Scheme (resolved decision #2):
      - First artist with a given name takes the bare slug (e.g. "echo").
      - Subsequent artists sharing that name get a metadata disambiguator
        appended: `{slug}-{genre}-{country_code}` (e.g. "echo-rap-us").
      - If metadata is insufficient or the disambiguator still collides,
        a numeric suffix is appended as a last resort (-2, -3, ...).

    All components are normalized the same way (lowercase, ASCII,
    hyphen-separated, leading/trailing hyphens stripped).
    """
    base = _normalize(artist_name) or "unknown"
    existing = existing_slugs or set()
    if base not in existing:
        return base

    parts = [base]
    if genre:
        parts.append(_normalize(genre))
    if country_code:
        parts.append(country_code.lower())
    candidate = "-".join(p for p in parts if p)

    if candidate != base and candidate not in existing:
        return candidate

    i = 2
    while f"{candidate}-{i}" in existing:
        i += 1
    return f"{candidate}-{i}"
