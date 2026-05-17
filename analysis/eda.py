"""Phase 0 EDA — empirical priors from the Soul Over AI corpus.

Inputs:  `analysis/soul-over-ai/` (vendored clone of xoundbyte/soul-over-ai)
Outputs:
  - `analysis/marker_priors.json` — marker frequencies, lift, co-occurrence, platform coverage
  - `analysis/calibration_set.json` — stratified 5-tier labeled set

Re-runnable with `python analysis/eda.py`; outputs are deterministic given a
fixed SOA snapshot and `RANDOM_SEED` below.

Phase 0 exit criterion (per dev plan): priors are non-uniform, calibration set
is frozen, and `docs/CALIBRATION_NOTES.md` lists ≥3 concrete rubric changes
that fall out of the data.
"""

from __future__ import annotations

import json
import logging
import random
from collections import Counter
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
SOA_DIR = ROOT / "soul-over-ai"
SOA_SRC = SOA_DIR / "src"
SOA_COMMIT_FILE = SOA_DIR / "COMMIT.txt"

PRIORS_OUT = ROOT / "marker_priors.json"
CALIBRATION_OUT = ROOT / "calibration_set.json"
HUMAN_CONTROLS = ROOT / "human_controls.json"

# Deterministic sampling. Don't change unless deliberately re-freezing the set.
RANDOM_SEED = 20260517
TIER_SIZE = 50  # per the dev plan's five strata of 50 each

# SOA's marker enum — read from analysis/soul-over-ai/artist.schema.json.
# Hard-coded here because we want the EDA to fail loudly if SOA's schema
# drifts (we'd need to re-evaluate which markers belong in our taxonomy).
SOA_MARKERS = [
    "2024-onwards",
    "ai-visuals",
    "anonymous",
    "high-output",
    "inconsistent-style",
]
PLATFORMS = ["spotify", "apple", "amazon", "youtube", "tiktok", "instagram"]
DISCLOSED_TIER = frozenset({"confirmed", "full"})


# --- Load corpus ------------------------------------------------------------


def load_soa_corpus() -> list[dict]:
    """Load every active (non-removed) SOA entry."""
    if not SOA_SRC.is_dir():
        raise RuntimeError(
            f"Soul Over AI not vendored at {SOA_SRC}. "
            "Run: gh repo clone xoundbyte/soul-over-ai analysis/soul-over-ai"
        )
    entries: list[dict] = []
    skipped = 0
    for p in sorted(SOA_SRC.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("skipped malformed file: %s", p.name)
            skipped += 1
            continue
        if data.get("removed"):
            continue
        entries.append(data)
    logger.info("Loaded %d active entries (%d malformed skipped)", len(entries), skipped)
    return entries


# --- Marker frequencies and lift -------------------------------------------


def compute_marker_frequencies(corpus: list[dict]) -> dict:
    """For each marker: raw freq, freq-when-disclosed, freq-when-undisclosed, lift."""
    n = len(corpus)
    disclosed = [e for e in corpus if e.get("disclosure") in DISCLOSED_TIER]
    undisclosed = [e for e in corpus if e.get("disclosure") == "none"]
    n_d = len(disclosed)
    n_u = len(undisclosed)

    result: dict[str, dict] = {}
    for marker in SOA_MARKERS:
        raw_count = sum(1 for e in corpus if marker in e.get("markers", []))
        d_count = sum(1 for e in disclosed if marker in e.get("markers", []))
        u_count = sum(1 for e in undisclosed if marker in e.get("markers", []))
        freq_d = d_count / n_d if n_d else 0.0
        freq_u = u_count / n_u if n_u else 0.0
        lift = (freq_d / freq_u) if freq_u > 0 else None
        result[marker] = {
            "raw_count": raw_count,
            "raw_freq": round(raw_count / n, 4) if n else 0.0,
            "disclosed_count": d_count,
            "freq_when_disclosed": round(freq_d, 4),
            "undisclosed_count": u_count,
            "freq_when_undisclosed": round(freq_u, 4),
            "lift": round(lift, 3) if lift is not None else None,
        }
    return result


# --- Co-occurrence matrix --------------------------------------------------


def compute_cooccurrence(corpus: list[dict]) -> dict:
    """Jaccard co-occurrence for each unordered marker pair (upper triangular)."""
    pair_counts: Counter = Counter()
    individual: Counter = Counter()
    for e in corpus:
        markers = set(e.get("markers", []))
        for m in markers:
            individual[m] += 1
        for a, b in combinations(sorted(markers), 2):
            pair_counts[(a, b)] += 1

    result: dict[str, dict] = {}
    for (a, b), c in sorted(pair_counts.items()):
        union = individual[a] + individual[b] - c
        jaccard = c / union if union else 0.0
        result[f"{a}|{b}"] = {"count": c, "jaccard": round(jaccard, 4)}
    return result


# --- Platform coverage -----------------------------------------------------


def compute_platform_coverage(corpus: list[dict]) -> dict:
    """Platform presence fractions for all entries and disclosed-AI subset."""
    n = len(corpus)
    disclosed = [e for e in corpus if e.get("disclosure") in DISCLOSED_TIER]
    n_d = len(disclosed)
    result: dict[str, dict] = {}
    for plat in PLATFORMS:
        all_count = sum(1 for e in corpus if e.get(plat))
        d_count = sum(1 for e in disclosed if e.get(plat))
        result[plat] = {
            "all_count": all_count,
            "all_fraction": round(all_count / n, 4) if n else 0.0,
            "disclosed_count": d_count,
            "disclosed_fraction": round(d_count / n_d, 4) if n_d else 0.0,
        }
    return result


# --- Distribution snapshots ------------------------------------------------


def compute_disclosure_distribution(corpus: list[dict]) -> dict:
    counter = Counter(e.get("disclosure") for e in corpus)
    return dict(counter)


def compute_shscore_population(corpus: list[dict]) -> dict:
    """Verify dev-plan claim: shScore is null across the corpus."""
    populated = sum(1 for e in corpus if e.get("shScore") is not None)
    return {
        "populated": populated,
        "total": len(corpus),
        "populated_fraction": round(populated / len(corpus), 4) if corpus else 0.0,
    }


def compute_disclosure_types_coverage(corpus: list[dict]) -> dict:
    """Newer SOA field — what AI usage type is disclosed (instrumentation/lyrics/etc.)."""
    type_counter: Counter = Counter()
    populated = 0
    for e in corpus:
        types = e.get("disclosureTypes") or []
        if types:
            populated += 1
            for t in types:
                type_counter[t] += 1
    return {
        "entries_with_types": populated,
        "fraction_populated": round(populated / len(corpus), 4) if corpus else 0.0,
        "type_counts": dict(type_counter),
    }


# --- Calibration set -------------------------------------------------------


def _make_calibration_entry(e: dict, tier: int, expected_label: str) -> dict:
    return {
        "id": e["id"],
        "name": e["name"],
        "source_tier": tier,
        "expected_label": expected_label,
        "soa_disclosure": e.get("disclosure"),
        "soa_markers": e.get("markers", []),
        "spotify": e.get("spotify"),
        "apple": e.get("apple"),
        "youtube": e.get("youtube"),
    }


def build_calibration_set(corpus: list[dict], human_controls: list[dict] | None = None) -> list[dict]:
    """Five-tier stratified sample per the dev plan.

    Tiers 1–4 sampled from SOA. Tier 5 (human controls) sourced from a
    separate, manually curated `analysis/human_controls.json` file.
    """
    tier1_pool = [e for e in corpus if e.get("disclosure") in DISCLOSED_TIER]
    tier2_pool = [e for e in corpus if e.get("disclosure") == "partial"]
    tier3_pool = [
        e for e in corpus
        if e.get("disclosure") == "none" and len(e.get("markers") or []) >= 3
    ]
    tier4_pool = [
        e for e in corpus
        if e.get("disclosure") == "none" and len(e.get("markers") or []) <= 1
    ]

    logger.info(
        "Tier pool sizes: t1=%d t2=%d t3=%d t4=%d",
        len(tier1_pool), len(tier2_pool), len(tier3_pool), len(tier4_pool),
    )

    result: list[dict] = []
    for tier_id, pool, label in [
        (1, tier1_pool, "ai"),
        (2, tier2_pool, "likely_ai"),
        (3, tier3_pool, "likely_ai"),
        (4, tier4_pool, "unclear"),
    ]:
        sample = random.sample(pool, min(TIER_SIZE, len(pool)))
        for e in sample:
            result.append(_make_calibration_entry(e, tier_id, label))

    if human_controls:
        for h in human_controls[:TIER_SIZE]:
            result.append({
                "id": h.get("id") or h.get("slug"),
                "name": h["name"],
                "source_tier": 5,
                "expected_label": "human",
                "soa_disclosure": None,
                "soa_markers": [],
                "spotify": h.get("spotify"),
                "apple": h.get("apple"),
                "youtube": h.get("youtube"),
                "note": h.get("note"),
            })
    else:
        logger.warning(
            "Tier 5 (human controls) empty. Populate %s to complete the set.",
            HUMAN_CONTROLS.name,
        )

    return result


# --- Main ------------------------------------------------------------------


def _soa_commit() -> str | None:
    if SOA_COMMIT_FILE.exists():
        return SOA_COMMIT_FILE.read_text(encoding="utf-8").strip()
    return None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    random.seed(RANDOM_SEED)

    corpus = load_soa_corpus()

    commit = _soa_commit()
    priors = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "corpus_source": f"xoundbyte/soul-over-ai@{commit}" if commit else "xoundbyte/soul-over-ai",
        "corpus_size_active": len(corpus),
        "random_seed": RANDOM_SEED,
        "disclosure_distribution": compute_disclosure_distribution(corpus),
        "markers": compute_marker_frequencies(corpus),
        "cooccurrence": compute_cooccurrence(corpus),
        "platform_coverage": compute_platform_coverage(corpus),
        "shscore_population": compute_shscore_population(corpus),
        "disclosure_types_coverage": compute_disclosure_types_coverage(corpus),
    }
    PRIORS_OUT.write_text(json.dumps(priors, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %s", PRIORS_OUT)

    human_controls: list[dict] = []
    if HUMAN_CONTROLS.exists():
        try:
            human_controls = json.loads(HUMAN_CONTROLS.read_text(encoding="utf-8"))
            logger.info("Loaded %d human controls", len(human_controls))
        except json.JSONDecodeError:
            logger.warning("malformed human_controls.json — ignoring")

    calibration = build_calibration_set(corpus, human_controls)
    CALIBRATION_OUT.write_text(json.dumps(calibration, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %s (%d entries)", CALIBRATION_OUT, len(calibration))


if __name__ == "__main__":
    main()
