# ClAudio Investigator — Dev Plan

A GitHub-native, agent-driven public index of AI-generated music artists. Successor in spirit to Soul Over AI; structurally a metadata-fingerprint engine where a Claude Haiku 4.5 agent renders verdicts from free public APIs, with the issue tracker doubling as submission flow and evidence trail.

> **Drift notice (2026-05-18):** This plan still references Spotify throughout, but the Spotify Web API was paywalled behind a Premium subscription requirement in mid-2026. Spotify is **removed** from the tool stack. Deezer covers fan-count + track-duration signals; YouTube covers video durations as a fallback. `suno-duration-cap` and `popularity-follower-mismatch` are alive, just on different data sources. See `CLAUDE.md` for current state and `investigator/tools/__init__.py` for the live module list.
>
> Additional drift since this plan was written: Haiku → Sonnet escalation (`request_escalation` tool, triggers on name-variant mismatch / historical-gap+recent-burst / low-confidence). See `investigator/rubric.py` for the escalation prompt and `agent.py` for the model-swap loop.

---

## North Star

- **The repo is the product.** Curated data lives at `src/*.json`. Submissions arrive as issues. Investigations run in Actions. PRs to the index are how entries land. No external service to maintain.
- **The agent is the maintainer.** A single Haiku 4.5 agent owns each investigation end-to-end via tool use — picks which sources to query, how deep to dig, and what to conclude. No fixed pipeline.
- **Behavior over audio.** Metadata signals (release velocity, cross-platform presence, profile coherence) drive verdicts. Audio fingerprinting is deferred to a later phase, possibly indefinitely.
- **Anonymous and durable.** Repo runs under an alt account. No human moderation bottleneck. High-confidence entries re-investigate on a schedule. Soul Over AI's two failure modes — taxonomy collapse and maintainer burnout — are designed out.

---

## Architecture

```
[Issue Filed: "Investigate: Artist Name"]
            │
            ▼
[GitHub Actions: investigate.yml fires on label "investigate"]
            │
            ▼
[investigator/main.py — Python script in Actions runner]
            │
            ▼
[investigator/agent.py — Claude tool-use loop, model=claude-haiku-4-5]
            │
            ├──> [Tools call free APIs: iTunes, Spotify, YouTube,
            │     MusicBrainz, Discogs, Deezer, Last.fm, Genius]
            │
            ▼
[Structured verdict JSON + reasoning + evidence chain]
            │
            ▼
[Comment posted on issue with verdict + signals]
            │
            ├──> [If confidence ≥ AUTO_MERGE_THRESHOLD → PR opened to src/{slug}.json]
            ├──> [If 0.5 ≤ confidence < threshold → label "needs-review"]
            └──> [If confidence < 0.5 → comment, no PR, label "low-confidence"]

[Quarterly cron: re-investigate entries; demote/promote as signals shift]
```

---

## Repository Structure

```
claudio-investigator/
├── .github/
│   ├── workflows/
│   │   ├── investigate.yml        # main investigation flow
│   │   ├── reinvestigate.yml      # quarterly re-check cron
│   │   └── build-index.yml        # concatenate src/*.json → dist/artists.json
│   └── ISSUE_TEMPLATE/
│       └── investigate.yml        # structured submission template
├── src/                           # curated per-artist records (one JSON per slug)
│   ├── kaizuken.json
│   └── ...
├── dist/
│   └── artists.json               # generated, do not edit by hand
├── investigator/
│   ├── __init__.py
│   ├── main.py                    # CLI + GitHub Actions entry point
│   ├── agent.py                   # Claude tool-use orchestration loop
│   ├── tools/
│   │   ├── itunes.py
│   │   ├── spotify.py
│   │   ├── youtube.py
│   │   ├── musicbrainz.py
│   │   ├── discogs.py
│   │   ├── deezer.py
│   │   ├── lastfm.py
│   │   ├── genius.py
│   │   └── vision.py              # album-art analysis via Claude vision
│   ├── rubric.py                  # verdict schema, scoring rubric, prompts
│   ├── budget.py                  # cost ceiling enforcement
│   ├── github_io.py               # issue parsing, comments, PRs
│   └── schema.py                  # Pydantic models for verdict + record
├── tests/
│   ├── fixtures/                  # canned API responses for offline testing
│   ├── test_tools.py
│   ├── test_agent.py
│   └── test_rubric.py
├── docs/
│   ├── SIGNALS.md                 # explanation of each signal and what it means
│   └── METHODOLOGY.md             # public-facing methodology doc
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## Data Sources & Signal Stack

All sources below are free or have a free tier that comfortably covers expected volume. No paid subscriptions required.

### Primary catalog sources

| Source | Auth | Rate limit | What we extract |
|---|---|---|---|
| **iTunes Search API** | None | Generous, unenforced | Artist/album/track lookups, release dates, artwork URLs, country, genre |
| **Spotify Web API** | Client credentials | 180/min | Artist name/genres/popularity/followers, album release dates and types, track durations, popularity scores |
| **YouTube Data API v3** | API key | 10,000 units/day | Channel age, subscriber count, upload velocity, video durations, comment streams (sample) |
| **YouTube Music** | None (ytmusicapi unofficial) | Self-policed | Artist topic channels, album linkages |
| **Deezer Public API** | None | ~50 req / 5s | Cross-platform existence, fan count, album coverage |

### Cross-reference / signal sources

| Source | Auth | Rate limit | What we extract |
|---|---|---|---|
| **MusicBrainz** | None (UA required) | 1 req/sec | Existence (huge signal — absence = AI tell), relationships, label history, real-name links |
| **Discogs** | Free token | 60/min anon, 240/min auth | Physical release presence (strong human signal), label data, contributor metadata |
| **Last.fm** | API key | Generous | Listener count history, growth shape, tag patterns, scrobble-to-listener ratio |
| **Genius** | Free token | Generous | Lyrics for text-pattern analysis |

### Skipped

- **Apple Music API** — requires $99/yr developer membership; iTunes Search covers 90% of read-only needs
- **Amazon Music** — no public API
- **Pandora** — no useful API since the Rdio era
- **SoundCloud** — API closed to new apps since 2023
- **Spotify audio-features** — deprecated for new apps Nov 2024; replaced in our stack by behavior signals

### Signal taxonomy (markers Claude will flag)

Maintained in `docs/SIGNALS.md`. Initial set:

- `high-output` — >12 releases/year with no historical baseline
- `suno-duration-cap` — track durations cluster suspiciously near 2:00–2:30
- `popularity-follower-mismatch` — Spotify popularity high relative to followers (>1 SD)
- `no-musicbrainz` — no entry in MusicBrainz
- `no-physical-release` — no Discogs entry of any physical media
- `thin-cross-platform` — present on streaming but not on any niche platform (Bandcamp, Discogs, etc.)
- `placeholder-bio` — bio missing, AI-generated text patterns, or template-filled
- `synthetic-album-art` — vision-pass flags AI generation patterns (Midjourney/SD fingerprints)
- `recent-only-listener-history` — Last.fm listener curve is a step-function, not a growth curve
- `gpt-lyric-patterns` — semantic loops, characteristic GPT rhyme dependencies
- `no-live-presence` — zero concert listings (Songkick/Bandsintown), no venue tags
- `anonymous-project` — no individual humans named or linked
- `inconsistent-style` — wild genre swings across catalog
- `2024-onwards` — entire catalog dates from 2024 or later with no earlier presence

---

## Claude Agent Design

### Model & API parameters

- Model: `claude-haiku-4-5` (alias) or `claude-haiku-4-5-20251001` (pinned)
- `max_tokens`: 2048 per response
- Temperature: 0.2 (we want consistency, not creativity)
- Prompt caching: enabled on the system prompt + tool definitions (these are stable per-investigation)

### Tool schemas

Each source gets one or more tools. Schemas declared in `investigator/tools/*.py` and aggregated in `agent.py`. Example skeleton:

```python
TOOLS = [
    {
        "name": "lookup_itunes",
        "description": "Search iTunes for an artist. Returns artist metadata including release dates, album list, artwork URLs, and country. Use this as the first cheap broad-coverage call for any artist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artist_name": {"type": "string"},
                "country": {"type": "string", "default": "us"}
            },
            "required": ["artist_name"]
        }
    },
    {
        "name": "lookup_musicbrainz",
        "description": "Search MusicBrainz for an artist. Returns whether the artist has an entry, their MBID if so, relationships, and label history. ABSENCE OF AN ENTRY is itself a strong signal for AI-generated artists.",
        "input_schema": {
            "type": "object",
            "properties": {"artist_name": {"type": "string"}},
            "required": ["artist_name"]
        }
    },
    {
        "name": "get_spotify_artist",
        "description": "Get Spotify artist profile by Spotify ID. Returns popularity (0-100), follower count, genres, and image URL. Use the popularity-to-followers ratio as a signal.",
        "input_schema": {
            "type": "object",
            "properties": {"spotify_id": {"type": "string"}},
            "required": ["spotify_id"]
        }
    },
    {
        "name": "get_spotify_albums",
        "description": "Get all albums/singles by a Spotify artist. Returns release dates, types, and track counts. Used for release velocity analysis.",
        "input_schema": {
            "type": "object",
            "properties": {"spotify_id": {"type": "string"}},
            "required": ["spotify_id"]
        }
    },
    {
        "name": "get_youtube_channel",
        "description": "Get YouTube channel data by handle or channel ID. Returns creation date, subscriber count, video count, and recent upload velocity.",
        "input_schema": {
            "type": "object",
            "properties": {"identifier": {"type": "string"}},
            "required": ["identifier"]
        }
    },
    {
        "name": "analyze_album_art",
        "description": "Run a Claude vision pass on an album cover image URL. Returns assessment of AI generation likelihood and specific fingerprints (Midjourney/SD/etc.) detected.",
        "input_schema": {
            "type": "object",
            "properties": {"image_url": {"type": "string"}},
            "required": ["image_url"]
        }
    },
    {
        "name": "get_genius_lyrics",
        "description": "Fetch lyrics for an artist's tracks from Genius. Returns lyrics text for up to N tracks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artist_name": {"type": "string"},
                "max_tracks": {"type": "integer", "default": 3}
            },
            "required": ["artist_name"]
        }
    },
    {
        "name": "submit_verdict",
        "description": "Final action. Submit the structured verdict that ends the investigation. Call this exactly once when you have sufficient evidence. After calling this, the investigation ends.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["ai", "likely_ai", "unclear", "likely_human", "human"]},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "markers": {"type": "array", "items": {"type": "string"}},
                "evidence": {"type": "array", "items": {"type": "object"}},
                "reasoning": {"type": "string"},
                "auto_merge_recommended": {"type": "boolean"}
            },
            "required": ["verdict", "confidence", "markers", "reasoning"]
        }
    }
]
```

### Agent loop pseudocode

```python
def investigate(artist_name: str, hints: dict) -> Verdict:
    budget = Budget(max_iterations=12, max_tokens_total=20000, max_usd=0.50)
    messages = [{"role": "user", "content": build_initial_prompt(artist_name, hints)}]

    while budget.has_remaining():
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2048,
            system=SYSTEM_PROMPT,  # cached
            tools=TOOLS,            # cached
            messages=messages,
        )
        budget.charge(response.usage)

        if response.stop_reason == "end_turn":
            break  # agent gave up without submit_verdict — treat as low confidence

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            break

        # check for submit_verdict — terminal action
        for block in tool_use_blocks:
            if block.name == "submit_verdict":
                return Verdict(**block.input)

        # execute requested tools
        tool_results = []
        for block in tool_use_blocks:
            result = TOOL_REGISTRY[block.name](**block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result)
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return Verdict.budget_exhausted()
```

### System prompt outline

```
You are ClAudio Investigator, an analyst specialized in identifying AI-generated
music artists from publicly available metadata.

Your job: given an artist name, gather evidence using the available tools and
return a structured verdict via submit_verdict.

Available signals to flag (see SIGNALS.md): [list]

Investigation strategy:
1. Start with cheap broad calls (lookup_itunes, lookup_musicbrainz).
2. If MusicBrainz absence + suspicious release pattern, that's already strong
   evidence. Don't over-investigate obvious cases.
3. Use targeted follow-ups (Spotify catalog, YouTube channel) for velocity and
   coherence signals.
4. Run vision pass on album art only if other signals are ambiguous — it's the
   most expensive call.
5. Call submit_verdict as soon as you have enough evidence for confident judgment.

Confidence calibration:
- 0.9+: Multiple strong signals, no contradicting evidence. Auto-merge.
- 0.7–0.9: Strong indicators but some ambiguity. Auto-merge if 3+ markers.
- 0.5–0.7: Mixed signals. Flag needs-review.
- <0.5: Insufficient evidence. Do not flag.

NEVER call submit_verdict with confidence >0.7 based on fewer than two
independent signal categories.
```

---

## Verdict Schema

`src/{slug}.json` format:

```json
{
  "name": "Artist Name",
  "slug": "artist-name",
  "verdict": "ai" | "likely_ai" | "unclear" | "likely_human",
  "confidence": 0.92,
  "markers": ["high-output", "no-musicbrainz", "synthetic-album-art"],
  "evidence": [
    {
      "source": "musicbrainz",
      "finding": "no entry for this artist name",
      "weight": "high"
    },
    {
      "source": "spotify",
      "finding": "17 albums released in 2025, no prior releases before 2024",
      "weight": "high"
    }
  ],
  "platforms": {
    "spotify_id": "...",
    "youtube_channel": "...",
    "apple_id": "...",
    "deezer_id": "..."
  },
  "investigated_at": "2026-05-17T13:42:00Z",
  "model": "claude-haiku-4-5-20251001",
  "investigation_issue": 42,
  "reasoning": "Brief paragraph explaining the verdict for human readers."
}
```

---

## GitHub Actions Workflow

### `investigate.yml`

```yaml
name: Investigate Artist
on:
  issues:
    types: [opened, labeled]

jobs:
  investigate:
    if: contains(github.event.issue.labels.*.name, 'investigate')
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      issues: write
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python -m investigator.main investigate-from-issue
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          SPOTIFY_CLIENT_ID: ${{ secrets.SPOTIFY_CLIENT_ID }}
          SPOTIFY_CLIENT_SECRET: ${{ secrets.SPOTIFY_CLIENT_SECRET }}
          YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}
          DISCOGS_TOKEN: ${{ secrets.DISCOGS_TOKEN }}
          LASTFM_API_KEY: ${{ secrets.LASTFM_API_KEY }}
          GENIUS_TOKEN: ${{ secrets.GENIUS_TOKEN }}
          ISSUE_BODY: ${{ github.event.issue.body }}
          ISSUE_NUMBER: ${{ github.event.issue.number }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GH_REPO: ${{ github.repository }}
```

### `reinvestigate.yml`

```yaml
name: Quarterly Re-investigation
on:
  schedule:
    - cron: '0 6 1 */3 *'  # 06:00 UTC, 1st of every 3rd month
  workflow_dispatch:

jobs:
  reinvestigate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - run: python -m investigator.main reinvestigate-all
        env: # same secrets as above
```

### Issue template (`.github/ISSUE_TEMPLATE/investigate.yml`)

```yaml
name: Investigate Artist
description: Submit an artist for AI-detection investigation
title: "Investigate: "
labels: ["investigate"]
body:
  - type: input
    id: name
    attributes:
      label: Artist Name
      placeholder: e.g. Kaizuken
    validations: { required: true }
  - type: input
    id: spotify
    attributes:
      label: Spotify URL (if known)
  - type: input
    id: youtube
    attributes:
      label: YouTube Music URL (if known)
  - type: input
    id: apple
    attributes:
      label: Apple Music URL (if known)
  - type: textarea
    id: notes
    attributes:
      label: Submitter notes (optional)
      description: Anything specific that made you suspect this artist?
```

---

## Cost Controls

All hard limits enforced in `investigator/budget.py` and verified before each API call.

| Limit | Value | Rationale |
|---|---|---|
| Max tool-use iterations per investigation | 12 | Bounds runaway loops |
| Max total tokens per investigation | 20,000 | Bounds runaway context growth |
| Max USD per investigation | $0.50 | Hard kill switch in `budget.py` |
| `max_tokens` per response | 2,048 | Bounds single-response output |
| Vision passes per investigation | 2 | Most expensive call |

At Haiku 4.5 pricing ($1/MTok in, $5/MTok out), the median investigation should land at $0.03–0.10. The $0.50 ceiling exists for pathological cases, not normal operation.

---

## Phased Implementation

Designed so each phase produces a runnable artifact and Claude Code can scope per-phase.

### Phase 0 — Empirical priors from Soul Over AI (no code, no agent)

Goal: extract rubric-informing priors and a labeled calibration set from the existing Soul Over AI corpus before writing a single line of investigator code. This is the EDA phase. Output is data and notes, not infrastructure.

The Soul Over AI repo (`xoundbyte/soul-over-ai`) contains 1,375 active curated entries with structured fields: `markers`, `disclosure`, `urls`, `notes`, `genres`, `popularity`, `followers`, and platform IDs across Spotify/Apple/Amazon/YouTube/TikTok/Instagram. Roughly 17% of entries carry `confirmed` or `full` disclosure — that's our gold-positive set for calibration. The rest are community-flagged at varying confidence levels.

#### Tasks

1. **Clone SOA into the project under `analysis/soul-over-ai/`** (git submodule or vendored copy — your call, but vendor it if you want reproducibility against a frozen snapshot, since SOA is no longer maintained).

2. **Marker frequency analysis.** For each marker in the corpus, compute:
   - Raw frequency across all active entries
   - Frequency conditioned on `disclosure ∈ {confirmed, full}` (high-confidence positives)
   - Frequency conditioned on `disclosure == none` (community-flagged only)
   - Lift ratio: how much more common is each marker in disclosed-AI vs the baseline

3. **Marker co-occurrence matrix.** Build a `markers × markers` matrix showing which markers tend to appear together. This tells you which signals are redundant (high co-occurrence = same underlying tell from different angles) vs independent (low co-occurrence = covering different aspects of the AI fingerprint). The rubric should weight independent signals higher than redundant clusters.

4. **Platform coverage analysis.** What fraction of confirmed-AI entries have Spotify? YouTube? TikTok? Instagram? This sets realistic expectations for our cross-platform-presence signal — if 95% of confirmed AI artists have a Spotify ID, then *absence* of Spotify becomes a signal. If only 30% have TikTok, then absence of TikTok is noise.

5. **Genre / popularity distributions.** Are AI artists clustered in specific genres? What's the distribution of `popularity` and `followers` for confirmed-AI vs the broader Spotify ecosystem? This validates (or kills) the popularity-to-follower-ratio signal.

6. **Build the stratified calibration set** — `analysis/calibration_set.json`, 250 entries:
   - **50 from `disclosure ∈ {confirmed, full}`** — gold positives, near-zero ambiguity
   - **50 from `disclosure == partial`** — likely positives with some uncertainty
   - **50 from `disclosure == none` with 3+ markers** — strong community signal but unverified
   - **50 from `disclosure == none` with 0–1 markers** — genuinely ambiguous; this is where the rubric earns its keep
   - **50 human controls** — picker's choice from your own listening, must have MusicBrainz + Discogs entries and concert history

7. **Marker taxonomy review.** Compare SOA's marker set against our proposed taxonomy in `docs/SIGNALS.md`. What did they have that we missed? What did we propose that's untested in their data? Specifically: SOA's data shows `ai-visuals`, `anonymous`, `high-output`, `2024-onwards`, and `inconsistent-style` as the dominant markers — our taxonomy should treat these as primary and demote anything outside this set unless we have an empirical reason to include it.

8. **Identify dead signals.** The `shScore` field (SubmitHub probability) is null across all 1,375 entries — SOA tracked it as a schema field but never populated it. Drop SubmitHub from our signal stack assumptions; the data isn't there. Anything else in the SOA schema that turns out to be aspirationally-typed-but-empty should get the same treatment.

#### Deliverables

- `analysis/eda.ipynb` (or `analysis/eda.py` if you prefer scripts over notebooks) — reproducible EDA
- `analysis/marker_priors.json` — empirical marker weights and co-occurrence matrix in a format the rubric can consume directly
- `analysis/calibration_set.json` — 250-entry labeled set, frozen, used as Phase 2's acceptance bar
- `docs/CALIBRATION_NOTES.md` — written findings, especially anything that should change the rubric design before Phase 1 starts

#### Exit criterion

`marker_priors.json` exists and is non-trivially different from a uniform-weight assumption (i.e., the EDA actually changed your priors), `calibration_set.json` is frozen and ready for Phase 2 consumption, and `CALIBRATION_NOTES.md` lists at least three concrete changes to the rubric or signal taxonomy that fall out of the data. If the EDA produces zero rubric changes, you didn't dig deep enough — there are always surprises in a 1,375-entry labeled corpus.

### Phase 1 — Foundation (no agent, no Actions)

Goal: prove the data layer works.

- Repo skeleton per structure above
- Implement `tools/itunes.py`, `tools/musicbrainz.py`, `tools/spotify.py` (client credentials only)
- CLI: `python -m investigator.main gather "Artist Name"` dumps raw metadata to stdout
- No Claude integration yet
- Fixtures for offline testing in `tests/fixtures/`
- README with setup instructions

**Exit criterion:** can run `gather` on a known AI artist and a known human artist, see visibly different metadata shapes in the output.

### Phase 2 — Agent loop (local only)

Goal: prove tool use orchestration works end-to-end.

- Implement `agent.py` with the tool-use loop
- Implement `rubric.py` (system prompt, signal definitions, verdict schema)
- Implement `budget.py` with hard caps
- Add `tools/youtube.py`, `tools/discogs.py`, `tools/deezer.py`, `tools/lastfm.py`, `tools/genius.py`
- CLI: `python -m investigator.main investigate "Artist Name"` produces a verdict JSON to stdout
- Pydantic schemas for verdict and record in `schema.py`
- Tests with fixture-mocked tool calls

**Exit criterion:** running against the 250-entry `analysis/calibration_set.json` from Phase 0 yields >85% agreement with the gold-positive tier (disclosure=confirmed/full), >75% agreement with the partial-disclosure tier, and correctly identifies all 50 human controls as `likely_human` or `human`. The ambiguous tier (none-disclosure, 0–1 markers) is the diagnostic — Claude's confidence distribution on that tier tells you whether the rubric is well-calibrated or overconfident.

### Phase 3 — GitHub integration

Goal: end-to-end flow via issues.

- `investigate.yml` workflow
- `ISSUE_TEMPLATE/investigate.yml`
- `github_io.py` for issue body parsing, comment posting, PR creation
- Confidence-threshold routing (auto-merge vs needs-review vs reject)
- `dist/artists.json` build step on push to `src/`

**Exit criterion:** filing an issue triggers investigation, posts evidence comment, opens PR for high-confidence verdicts. End-to-end on alt repo with at least 3 real submissions.

### Phase 4 — Quality & longevity

Goal: keep the index honest over time.

- `reinvestigate.yml` quarterly cron
- Vision tool (`tools/vision.py`) for album art analysis
- `docs/METHODOLOGY.md` public-facing explainer
- Stats dashboard generated to `docs/stats.md` on each push (count by verdict, confidence distribution, marker frequency)
- Removal request flow (separate issue template, manual review)

**Exit criterion:** index contains 100+ entries, has run for one quarterly re-investigation cycle, has handled at least one removal request.

### Phase 5 (deferred) — Audio layer

Only consider once Phase 4 has been stable for 3+ months. Bolt on external classifier (Ircam Amplify / Sonauto / open-source) as one additional tool. Treat as tiebreaker, never primary evidence.

---

## Open Decisions for the Claude Code Session

These are deliberately unresolved and should be settled in the first scoping conversation:

1. **Auto-merge threshold.** Start at 0.90 conservative, or 0.85 to catch more cases at risk of more false positives? Recommend starting at 0.90 and lowering after Phase 3 calibration data.
2. **Slug collision handling.** Two artists named "Echo" — disambiguate by platform ID? Append a suffix?
3. **Schema compatibility with Soul Over AI.** Mirror their `src/{slug}.json` fields for drop-in replacement, or design fresh? Recommend fresh but keep the slug convention so existing tooling can interop.
4. **Removal request flow.** Same issue tracker with `remove` label, or separate process? Recommend same tracker, different label, lighter agent involvement (just confidence-check the original verdict).
5. **De-duplication of submissions.** If issue #5 and #47 are both for "Kaizuken," does the second one short-circuit to a comment linking the first, or re-investigate? Recommend short-circuit unless the existing entry is >90 days old.
6. **Caching of API responses across investigations.** Worth it for the source-of-truth platforms (MusicBrainz, Discogs); risky for velocity-sensitive ones (Spotify, YouTube). Recommend a 24-hour cache layer keyed by source+identifier.
7. **Anonymity scope.** Just the GitHub bot account, or also rotate API keys / use proxy? Probably just the account; over-engineering anonymity is a path to friction.
8. **License for the curated data.** CC-BY-SA (Soul Over AI's likely choice), CC0, or something stricter? Recommend CC-BY-SA so derivative work is allowed but attribution required.

---

## Pre-flight Checklist (for the Claude Code session)

Before writing any code, confirm:

- [ ] Decide alt-account name and create it
- [ ] Generate API keys: Spotify client credentials, YouTube Data API, Discogs personal token, Last.fm API key, Genius API token
- [ ] Get Anthropic API key with billing/credits attached
- [ ] Repo created under alt account, set public, branch protection on `main`
- [ ] Secrets uploaded to repo Actions settings
- [ ] Settle the eight open decisions above
- [ ] Pick a "ground truth" test set: 10 known AI artists, 10 known human artists. These become the Phase 2 acceptance bar.

---

## Reference: calibration set construction

The Phase 0 EDA produces `analysis/calibration_set.json` from the Soul Over AI corpus. The strata to draw from:

- **Tier 1 (50 gold positives):** entries with `disclosure ∈ {confirmed, full}` — 236 candidates in the corpus, sample 50
- **Tier 2 (50 likely positives):** entries with `disclosure == partial` — 180 candidates, sample 50
- **Tier 3 (50 community-flagged):** `disclosure == none` with 3+ markers — sample 50 stratified across genre/platform
- **Tier 4 (50 ambiguous):** `disclosure == none` with 0–1 markers — sample 50; these are the genuinely hard cases
- **Tier 5 (50 human controls):** picker's choice from your own listening, must satisfy: present in MusicBrainz, has Discogs physical release, has concert history (Songkick/Bandsintown), pre-2020 catalog start

Freeze the set as JSON in the repo. Re-running Phase 2 acceptance against the same frozen set is how you compare rubric iterations apples-to-apples.

---

## Reference Links

- Anthropic API docs: https://docs.claude.com/en/api/overview
- Claude tool use docs: https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview
- Haiku 4.5 model card: https://www.anthropic.com/claude/haiku
- iTunes Search API: https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/
- Spotify Web API: https://developer.spotify.com/documentation/web-api
- YouTube Data API: https://developers.google.com/youtube/v3
- MusicBrainz: https://musicbrainz.org/doc/MusicBrainz_API
- Discogs API: https://www.discogs.com/developers
- Last.fm API: https://www.last.fm/api
- Genius API: https://docs.genius.com/
- Soul Over AI sunset issue (for context): https://github.com/xoundbyte/soul-over-ai/issues/3714
