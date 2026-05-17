"""Phase 0 EDA — empirical priors from the Soul Over AI corpus.

Inputs: `analysis/soul-over-ai/` (vendored or submoduled clone of xoundbyte/soul-over-ai).
Outputs:
  - `analysis/marker_priors.json` — marker frequencies, co-occurrence, platform coverage
  - `analysis/calibration_set.json` — 250-entry stratified labeled set
  - prose findings → `docs/CALIBRATION_NOTES.md` (write up manually)

This is a single-file script by design. The EDA should be re-runnable end-to-end
with `python analysis/eda.py` and produce byte-identical outputs given the same
vendored SOA snapshot. Determinism: seed all sampling.

Phase 0 exit criterion (from the dev plan):
  - `marker_priors.json` is non-trivially different from a uniform prior
    (i.e., the EDA actually changed your priors).
  - `calibration_set.json` is frozen and ready for Phase 2 consumption.
  - `docs/CALIBRATION_NOTES.md` lists ≥3 concrete rubric or taxonomy changes
    that fall out of the data.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
SOA_SRC = ROOT / "soul-over-ai" / "src"  # SOA layout: src/*.json per artist
PRIORS_OUT = ROOT / "marker_priors.json"
CALIBRATION_OUT = ROOT / "calibration_set.json"

RANDOM_SEED = 20260517  # today's date — change only if regenerating from scratch


# --- 1. Load corpus ---------------------------------------------------------


def load_soa_corpus() -> list[dict]:
    """Load every JSON file under `analysis/soul-over-ai/src/` and return as list."""
    raise NotImplementedError(
        "Phase 0 — vendor SOA into analysis/soul-over-ai/, then implement this."
    )


# --- 2. Marker frequency analysis -------------------------------------------


def compute_marker_frequencies(corpus: list[dict]) -> dict:
    """For each marker, compute raw/disclosed/undisclosed frequency and lift ratio."""
    raise NotImplementedError("Phase 0.")


# --- 3. Marker co-occurrence ------------------------------------------------


def compute_cooccurrence(corpus: list[dict]) -> dict:
    """Upper-triangular co-occurrence matrix for the marker set."""
    raise NotImplementedError("Phase 0.")


# --- 4. Platform coverage ---------------------------------------------------


def compute_platform_coverage(corpus: list[dict]) -> dict:
    """For confirmed-AI entries, what fraction have Spotify/YouTube/TikTok/Insta?"""
    raise NotImplementedError("Phase 0.")


# --- 5. Calibration set -----------------------------------------------------


def build_calibration_set(corpus: list[dict], human_controls: list[dict]) -> list[dict]:
    """Sample the five tiers per the dev plan / analysis/README.md."""
    raise NotImplementedError("Phase 0.")


# --- 6. Main ----------------------------------------------------------------


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    random.seed(RANDOM_SEED)

    corpus = load_soa_corpus()
    logger.info("Loaded %d entries from SOA", len(corpus))

    priors = {
        "generated_at": "TBD",
        "corpus_size": len(corpus),
        "markers": compute_marker_frequencies(corpus),
        "cooccurrence": compute_cooccurrence(corpus),
        "platform_coverage": compute_platform_coverage(corpus),
    }
    PRIORS_OUT.write_text(json.dumps(priors, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("Wrote %s", PRIORS_OUT)

    # Human controls list is built manually — see analysis/human_controls.json (Phase 0).
    human_controls_path = ROOT / "human_controls.json"
    human_controls = json.loads(human_controls_path.read_text(encoding="utf-8"))

    calibration = build_calibration_set(corpus, human_controls)
    CALIBRATION_OUT.write_text(
        json.dumps(calibration, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    logger.info("Wrote %s (%d entries)", CALIBRATION_OUT, len(calibration))


if __name__ == "__main__":
    main()
