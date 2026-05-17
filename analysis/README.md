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
- **Tier 5 (50):** Human controls — picker's choice from your own listening, must satisfy ALL of:
  - present in MusicBrainz (has an MBID)
  - has Discogs physical release (vinyl, CD, or cassette pressing)
  - has concert history (Songkick / Bandsintown listings or documented tours)
  - pre-2020 catalog start (earliest release ≥ 5 years old)

## Populating tier 5 — `human_controls.json`

Copy `human_controls.template.json` to `human_controls.json` and replace the
example entries with your 50 picks. The template has three worked examples
showing the expected fields; the criteria above all four must hold for each
entry.

**Field reference:**

| Field | Required | How to find it |
|---|---|---|
| `id` | yes | a lowercase-hyphenated slug for the artist (any unique identifier works) |
| `name` | yes | display name as it appears in MusicBrainz |
| `spotify` | recommended | the 22-char ID from `open.spotify.com/artist/{id}` |
| `apple` | optional | the numeric ID from `music.apple.com/.../artist/{name}/{id}` |
| `youtube` | optional | the channel ID (`UC...`) from `youtube.com/channel/{id}` |
| `note` | recommended | one-line note citing your evidence for the four criteria (MBID, a Discogs release, a tour year, a debut year) |

**Picking strategy:**

- Use your own listening — the dev plan explicitly calls for "picker's choice
  from your own listening."
- Mix genres deliberately. 50 indie-rock artists would over-fit the
  calibration to one sound; pick across rock, hip-hop, electronic, jazz, folk,
  classical, world, etc.
- Mix eras. Some legacy artists (Aretha Franklin, Joni Mitchell) and some
  contemporary (Bon Iver, Phoebe Bridgers) — diversity helps catch rubric
  failures that correlate with age of catalog.
- Easy bar to clear: anyone with a Wikipedia page, a Bandcamp with vinyl, and
  documented tours will satisfy all four. If you're unsure about an artist,
  pick someone else.

Once `human_controls.json` exists, re-run `python analysis/eda.py` and the
tier-5 entries will be appended to `calibration_set.json` automatically.

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
