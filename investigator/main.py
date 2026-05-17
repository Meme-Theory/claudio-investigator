"""CLI entry point for ClAudio Investigator.

Subcommands:
  - gather              Phase 1 — dump raw API metadata for an artist, no agent.
  - investigate         Phase 2 — full agent investigation, prints verdict JSON.
  - investigate-from-issue   Phase 3 — read ISSUE_BODY env, post comment + PR.
  - reinvestigate-all   Phase 4 — quarterly cron entry point.

Invoke as `python -m investigator.main <subcommand>` or via the `claudio`
console script defined in pyproject.toml.
"""

from __future__ import annotations

import json
import logging
import sys

import click

logger = logging.getLogger(__name__)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
def cli(verbose: bool) -> None:
    """ClAudio Investigator command line."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@cli.command()
@click.argument("artist_name")
@click.option("--spotify-id", help="Skip Spotify search and use this artist ID.")
def gather(artist_name: str, spotify_id: str | None) -> None:
    """Phase 1 — dump raw metadata. No agent, no verdict.

    Used to verify that the data layer produces visibly different shapes for
    known-AI vs known-human artists before wiring the agent.
    """
    raise NotImplementedError("Phase 1 — implement against tools/* once data layer lands.")


@cli.command()
@click.argument("artist_name")
@click.option("--spotify-url", default=None)
@click.option("--youtube-url", default=None)
@click.option("--apple-url", default=None)
@click.option("--notes", default=None, help="Submitter notes / hints.")
@click.option(
    "--transcript/--no-transcript",
    default=False,
    help="Include the full per-turn transcript in the output (verbose).",
)
def investigate(
    artist_name: str,
    spotify_url: str | None,
    youtube_url: str | None,
    apple_url: str | None,
    notes: str | None,
    transcript: bool,
) -> None:
    """Phase 2 — full investigation. Prints a Verdict JSON to stdout."""
    from .agent import investigate as run_investigation

    hints = {
        k: v
        for k, v in {
            "spotify_url": spotify_url,
            "youtube_url": youtube_url,
            "apple_url": apple_url,
            "submitter_notes": notes,
        }.items()
        if v
    }
    result = run_investigation(artist_name, hints)
    payload: dict = {
        "artist": artist_name,
        "verdict": result.verdict.model_dump() if result.verdict else None,
        "terminated_by": result.terminated_by,
        "budget": result.budget.summary(),
        "model": result.model,
        "completed_at": result.completed_at.isoformat(),
    }
    if result.error:
        payload["error"] = result.error
    if transcript:
        payload["transcript"] = result.transcript
    click.echo(json.dumps(payload, indent=2, default=str))


@cli.command("investigate-from-issue")
def investigate_from_issue() -> None:
    """Phase 3 — read ISSUE_BODY / ISSUE_NUMBER from env, run, post results.

    Designed to run inside `.github/workflows/investigate.yml`. Routes by label:
      - `investigate` label → fresh investigation of a newly submitted artist.
      - `remove` label → re-investigate an existing entry; demote / remove
        only if signals have shifted below `likely_ai`.

    Side effects in both cases:
      - Posts a comment with the verdict + evidence on the originating issue.
      - Opens a PR against `src/{slug}.json` if confidence ≥ AUTO_MERGE_THRESHOLD
        (or, for removals, a PR deleting the file if the new verdict demotes).
      - Applies labels: 'needs-review' or 'low-confidence' as appropriate.
    """
    raise NotImplementedError("Phase 3 — implement against github_io.")


@cli.command("reinvestigate-all")
@click.option("--limit", type=int, default=None, help="Cap entries for one run.")
def reinvestigate_all(limit: int | None) -> None:
    """Phase 4 — walk src/*.json and re-investigate each entry.

    Verdicts can shift over time as platforms reveal more data (or wipe it).
    Triggered by `.github/workflows/reinvestigate.yml` on cron.
    """
    raise NotImplementedError("Phase 4 — implement after Phase 3 settles.")


def main() -> None:
    """Entry point so `python -m investigator.main` works."""
    cli(prog_name="claudio")


if __name__ == "__main__":
    sys.exit(main())
