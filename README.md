# ClAudio Investigator

An agent-driven, GitHub-native public index of AI-generated music artists. A Claude Haiku 4.5 agent investigates each submitted artist using free music APIs (iTunes, Spotify, YouTube, MusicBrainz, Discogs, Deezer, Last.fm, Genius), renders a structured verdict with evidence and signal markers, and lands curated entries as PRs against `src/{slug}.json`.

Successor in spirit to [Soul Over AI](https://github.com/xoundbyte/soul-over-ai). Structurally a metadata-fingerprint engine — the issue tracker is the submission flow, Actions run the investigations, the repo is the product.

## Status

Project genesis — scaffolding only. No investigation code is implemented yet. See `CLAUDIO_INVESTIGATOR_DEV_PLAN_1.md` for the full phased plan.

| Phase | Goal | Status |
|---|---|---|
| 0 | EDA on Soul Over AI corpus, calibration set | pending |
| 1 | Data layer (tools, no agent) | pending |
| 2 | Agent loop end-to-end | pending |
| 3 | GitHub Actions integration | pending |
| 4 | Re-investigation cron, vision pass, methodology | pending |
| 5 | Audio classifier (deferred) | deferred |

## How it works (intended)

1. Someone files an issue with the `investigate` label naming an artist.
2. `investigate.yml` fires; the runner invokes the Claude Haiku 4.5 agent in `investigator/agent.py`.
3. The agent picks which APIs to query through tool-use — iTunes for broad coverage, MusicBrainz for ground truth (absence is a signal), Spotify for velocity/popularity, YouTube for channel age, Discogs for physical-release presence, vision for album-art fingerprints.
4. The agent submits a verdict (`ai | likely_ai | unclear | likely_human | human`) with confidence, markers, evidence, and reasoning.
5. High-confidence verdicts auto-open a PR to `src/{slug}.json`. Mid-confidence get a `needs-review` label. Low-confidence stop at a comment.
6. A quarterly cron re-investigates entries; verdicts can shift as new evidence accumulates.

## Setup (local dev)

```bash
python -m venv .venv
.venv\Scripts\activate           # PowerShell
pip install -e ".[dev,analysis]"
cp .env.example .env             # fill in API keys
```

Required env vars:

- `ANTHROPIC_API_KEY`
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`
- `YOUTUBE_API_KEY`
- `DISCOGS_TOKEN`
- `LASTFM_API_KEY`
- `GENIUS_TOKEN`

See `.env.example` for the full list.

## Repo layout

```
investigator/         agent + tools + rubric + schema
  tools/              one module per data source
src/                  curated per-artist records ({slug}.json)
dist/                 generated artists.json (built, not edited)
analysis/             Phase 0 EDA against Soul Over AI corpus
.github/workflows/    investigate / reinvestigate / build-index
docs/                 SIGNALS, METHODOLOGY, CALIBRATION_NOTES
tests/                pytest + fixtures
```

## Methodology

See `docs/METHODOLOGY.md` (drafted in Phase 4) for the public-facing explainer and `docs/SIGNALS.md` for the marker taxonomy.

## License

- **Code** — MIT. See `LICENSE`.
- **Curated data** (`src/` and `dist/artists.json`) — Open Database License (ODbL) v1.0, with record contents under the Database Contents License (DbCL) v1.0. See `LICENSE-data`.

Downstream uses of the database must attribute as: *"Contains information from ClAudio Investigator, made available under the Open Database License (ODbL)."*
