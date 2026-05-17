# analysis/ — Phase 0 EDA

This directory is the home of the empirical-priors work that precedes any investigator code. Do Phase 0 here before writing anything in `investigator/`.

## Deliverables

- `soul-over-ai/` — vendored or submoduled clone of the SOA repo. Vendor it if you want a frozen snapshot (SOA is no longer maintained).
- `eda.py` (or `eda.ipynb`) — reproducible analysis script.
- `marker_priors.json` — empirical marker weights and co-occurrence matrix in a format the rubric can consume directly. See schema below.
- `calibration_set.json` — 250-entry stratified labeled set, frozen, used as Phase 2's acceptance bar.
- Companion writeup: `../docs/CALIBRATION_NOTES.md` lists at least three concrete rubric or taxonomy changes that fall out of the data.

## Strata for `calibration_set.json`

- **Tier 1 (50):** SOA entries with `disclosure ∈ {confirmed, full}` — gold positives, near-zero ambiguity
- **Tier 2 (50):** SOA entries with `disclosure == partial` — likely positives with some uncertainty
- **Tier 3 (50):** SOA entries with `disclosure == none` AND 3+ markers — strong community signal, unverified
- **Tier 4 (50):** SOA entries with `disclosure == none` AND 0–1 markers — genuinely ambiguous; where the rubric earns its keep
- **Tier 5 (50):** Human controls — picker's choice, must satisfy:
  - present in MusicBrainz
  - has Discogs physical release
  - has concert history (Songkick / Bandsintown)
  - pre-2020 catalog start

## `marker_priors.json` schema

```jsonc
{
  "generated_at": "2026-05-17T...",
  "corpus_size": 1375,
  "markers": {
    "ai-visuals": {
      "raw_freq": 0.42,
      "freq_when_disclosed": 0.81,
      "freq_when_undisclosed": 0.35,
      "lift": 2.31
    },
    // ...one per marker observed in SOA...
  },
  "cooccurrence": {
    "ai-visuals|anonymous": 0.67,
    // ...upper-triangular pairs...
  },
  "platform_coverage": {
    "spotify": 0.95,
    "youtube": 0.62,
    // ...for disclosed-AI entries only...
  }
}
```

## What changes if EDA findings disagree with our priors

- **`SIGNAL_MARKERS` order in `investigator/rubric.py`** — re-sort by empirical lift.
- **`SUBMIT_VERDICT_TOOL` enum in `rubric.py`** — drop markers that don't earn it; add markers that fall out of SOA's data that we missed.
- **`docs/SIGNALS.md`** — keep in lock-step with the marker list.
- **`docs/CALIBRATION_NOTES.md`** — write down what changed and why.

## Reproducibility

- Vendor SOA at a specific commit (`analysis/soul-over-ai/COMMIT.txt`) so re-running EDA later produces identical priors.
- `eda.py` should be idempotent: re-running with no code change produces byte-identical `marker_priors.json` and `calibration_set.json`.
