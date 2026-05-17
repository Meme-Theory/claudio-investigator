# ClAudio Investigator

Agent-driven public index of AI-generated music artists. GitHub-native: issues are submissions, Actions run investigations, PRs to `src/*.json` are how entries land. A Claude Haiku 4.5 agent owns each investigation via tool-use over free public music APIs.

**Spec of record:** `CLAUDIO_INVESTIGATOR_DEV_PLAN_1.md` at repo root. Everything below is a quick-reference; the dev plan is authoritative when they conflict.

## Current state

Scaffolding complete (this session, 2026-05-17). No Phase code written yet.

**Next:** Phase 0 — empirical priors EDA against the Soul Over AI corpus. No investigator code until Phase 0 deliverables exist (`analysis/marker_priors.json`, `analysis/calibration_set.json`, `docs/CALIBRATION_NOTES.md`).

Phases (from dev plan §"Phased Implementation"):
- **Phase 0** — EDA on Soul Over AI corpus → empirical marker weights + calibration set
- **Phase 1** — Data layer (iTunes/MusicBrainz/Spotify tools, no agent)
- **Phase 2** — Agent loop end-to-end, local CLI
- **Phase 3** — GitHub Actions integration (issues → investigations → PRs)
- **Phase 4** — Quarterly re-investigation, vision tool, methodology docs
- **Phase 5** (deferred) — Audio classifier as tiebreaker tool

## Repo layout

```
investigator/         # Python package (agent, tools, rubric, schema)
  tools/              # one file per API (itunes, spotify, musicbrainz, ...)
src/                  # curated per-artist records: one {slug}.json each
dist/                 # generated artists.json (don't hand-edit)
analysis/             # Phase 0 EDA: SOA clone, eda.py, priors, calibration set
.github/workflows/    # investigate / reinvestigate / build-index
tests/                # pytest, fixtures for offline tool tests
docs/                 # SIGNALS.md (taxonomy), METHODOLOGY.md (public), CALIBRATION_NOTES.md
```

## Stack

- Python 3.12
- `anthropic` SDK (Haiku 4.5: `claude-haiku-4-5` alias, `claude-haiku-4-5-20251001` pinned)
- `pydantic` v2 for schema
- `requests` for HTTP, `python-dotenv` for local env
- `click` for CLI entry (`python -m investigator.main ...`)
- pytest for tests
- GitHub Actions for orchestration

## Key conventions

- **Model:** Haiku 4.5 ONLY for investigation. No Opus, no Sonnet — the rubric is supposed to work cheap.
- **Prompt caching:** system prompt + tool schemas cached per investigation (they're stable).
- **Tool-use loop terminates on `submit_verdict`** (declared as a tool, but acts as a sentinel — see `investigator/agent.py`).
- **Budget is enforced before every API call**, not just at the end (`investigator/budget.py`).
- **Verdicts have five values:** `ai | likely_ai | unclear | likely_human | human`. No booleans.
- **One JSON file per artist** under `src/{slug}.json`. Slug = lowercase, hyphenated, ASCII.
- **Never edit `dist/artists.json` by hand** — it's built from `src/`.
- **Tool functions return plain dicts** (not Pydantic) — the agent serializes them as `tool_result` content.
- **Tests mock HTTP at the requests boundary** (`responses` library). Don't mock our own tool functions.

## Env vars

See `.env.example`. Required for full operation:

- `ANTHROPIC_API_KEY` — Claude API
- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` — client-credentials flow
- `YOUTUBE_API_KEY` — Data API v3
- `DISCOGS_TOKEN` — personal access token
- `LASTFM_API_KEY` — generous free tier
- `GENIUS_TOKEN` — for lyric retrieval

`MUSICBRAINZ_USER_AGENT` should be set to a descriptive UA per their policy.

## Don'ts (project-specific traps)

- **Don't add paid APIs.** Apple Music ($99/yr), Amazon Music, SoundCloud — all explicitly out of scope. Stay free-tier.
- **Don't use Spotify audio-features.** Deprecated for new apps Nov 2024. Replaced by behavior signals.
- **Don't add audio fingerprinting yet.** Phase 5, deferred. Don't pull it forward without a plan-update.
- **Don't grow the marker set on a hunch.** Markers earn their place via EDA lift ratios (Phase 0). Adding a marker means re-running the calibration set.
- **Don't let the agent loop run unbounded.** `budget.py` enforces 12 iterations / 20k tokens / $0.50 — never relax these in code, only via deliberate config.
- **Don't auto-merge PRs below the configured threshold.** Default 0.90 confidence (open decision #1).

## Decisions

### Resolved 2026-05-17

- **License:** MIT for code, ODbL v1.0 for the curated data (record contents under DbCL v1.0). See `LICENSE` and `LICENSE-data`.
- **Slug collision:** First artist with a given name takes the bare slug; subsequent collisions get a `{slug}-{genre}-{country_code}` disambiguator (e.g. `echo`, then `echo-rap-us`). Numeric suffix is the last-resort fallback. Implemented in `investigator/github_io.py::slug_for`.
- **Anonymity:** Public attribution under the user's real GitHub account. No proxy/rotation. Drop "alt account" framing wherever you find it.
- **Removal flow:** Same issue tracker, `remove` label, agent re-investigates. Template at `.github/ISSUE_TEMPLATE/remove.yml`. `investigate.yml` triggers on both `investigate` and `remove`; `main.py::investigate-from-issue` routes by label.

### Pending (deferred to the data or phase that will inform them)

1. **Auto-merge threshold** (default 0.90) — re-tune after Phase 2 calibration-set confidence distribution lands.
2. **Schema compatibility with Soul Over AI** — Phase 0 EDA will reveal which SOA fields are populated vs aspirational; settle then. Slug convention is already compatible.
3. **Submission dedup window** (lean: short-circuit if existing entry <90d old) — settle once Phase 3 sees real submission cadence.
4. **API response caching** (lean: 24h cache for MusicBrainz/Discogs, no cache for Spotify/YouTube) — Phase 1/2 engineering decision; settle when tools come online.

## Pre-flight checklist

- [ ] API keys generated (Spotify, YouTube, Discogs, Last.fm, Genius)
- [ ] Anthropic API key with billing
- [ ] GitHub repo created under user's account, public, main protected
- [ ] Secrets uploaded to Actions
- [ ] Pending decisions tracked but not blocking; revisit at their owning phase
- [ ] Phase 2 ground-truth test set (10 AI + 10 human) selected

## Running things (once implemented)

```bash
# Phase 0 EDA
python analysis/eda.py

# Phase 1 — raw metadata gather, no agent
python -m investigator.main gather "Artist Name"

# Phase 2 — full agent investigation, local
python -m investigator.main investigate "Artist Name"

# Phase 3 — from a GitHub issue (used by Actions)
python -m investigator.main investigate-from-issue

# Quarterly cron (Phase 4)
python -m investigator.main reinvestigate-all
```

## Cost ceiling

Per investigation: $0.50 hard kill, 12 iterations, 20k tokens, 2 vision passes. Median expected $0.03–0.10 at Haiku 4.5 pricing.
