"""One-shot backfill: seed data/investigations.jsonl from prior manual-investigate
GitHub Actions runs.

Walks every successful run of the `Manual investigation` workflow, downloads
its `verdict-{run_id}` artifact via the GH REST API (gh CLI), unpacks
verdict.json, flattens to the same shape the workflow now appends, and writes
one line per run to data/investigations.jsonl, sorted by completed_at.

Run from repo root:
    python scripts/backfill_ledger.py
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = "Meme-Theory/claudio-investigator"
WORKFLOW = "manual-investigate.yml"
LEDGER = Path("data/investigations.jsonl")


def gh(args: list[str]) -> bytes:
    """Run gh CLI, return stdout bytes."""
    out = subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
    )
    return out.stdout


def list_runs() -> list[dict]:
    raw = gh(
        [
            "run",
            "list",
            "--workflow",
            WORKFLOW,
            "--limit",
            "100",
            "--json",
            "databaseId,conclusion,createdAt,displayTitle",
        ]
    )
    runs = json.loads(raw)
    return [r for r in runs if r["conclusion"] == "success"]


def run_artifacts(run_id: int) -> list[dict]:
    raw = gh(["api", f"repos/{REPO}/actions/runs/{run_id}/artifacts"])
    return json.loads(raw)["artifacts"]


def download_verdict(artifact_id: int) -> dict | None:
    raw = gh(["api", f"repos/{REPO}/actions/artifacts/{artifact_id}/zip"])
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            with z.open("verdict.json") as f:
                data = f.read()
                if not data.strip():
                    return None
                return json.loads(data)
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as e:
        print(f"  ! could not parse artifact {artifact_id}: {e}", file=sys.stderr)
        return None


def to_ledger_row(verdict_doc: dict, run_id: int) -> dict:
    v = verdict_doc.get("verdict") or {}
    return {
        "artist": verdict_doc.get("artist"),
        "verdict": v.get("verdict"),
        "confidence": v.get("confidence"),
        "markers": v.get("markers", []),
        "evidence": v.get("evidence", []),
        "reasoning": v.get("reasoning"),
        "auto_merge_recommended": v.get("auto_merge_recommended", False),
        "model": verdict_doc.get("model"),
        "terminated_by": verdict_doc.get("terminated_by"),
        "budget": verdict_doc.get("budget"),
        "completed_at": verdict_doc.get("completed_at"),
        "error": verdict_doc.get("error"),
        "run_id": str(run_id),
        "run_url": f"https://github.com/{REPO}/actions/runs/{run_id}",
    }


def main() -> int:
    runs = list_runs()
    print(f"Found {len(runs)} successful manual-investigate runs.")

    rows: list[dict] = []
    for r in runs:
        rid = r["databaseId"]
        title = r["displayTitle"]
        print(f"- run {rid}  {title}")
        artifacts = run_artifacts(rid)
        verdict_artifact = next(
            (a for a in artifacts if a["name"] == f"verdict-{rid}" and not a["expired"]),
            None,
        )
        if not verdict_artifact:
            print(f"  ! no verdict artifact (expired or missing) — skipping")
            continue
        doc = download_verdict(verdict_artifact["id"])
        if not doc:
            continue
        rows.append(to_ledger_row(doc, rid))

    rows.sort(key=lambda r: r.get("completed_at") or "")

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")

    print(f"Wrote {len(rows)} rows to {LEDGER}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
