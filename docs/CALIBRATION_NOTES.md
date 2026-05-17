# Calibration Notes

**Status:** Phase 0 complete (2026-05-17). EDA ran against Soul Over AI corpus at commit `c9e2e0f036a04d4f9f62b2614912b96bcdc8c017`. 1,375 active entries analyzed.

Outputs:
- `analysis/marker_priors.json` — frozen empirical priors
- `analysis/calibration_set.json` — 200 entries across tiers 1–4 (tier 5 pending manual human controls — see `analysis/human_controls.template.json`)

## Headline findings

### 1. SOA's marker enum is tiny (5) vs. our proposed taxonomy (14)

Of our 14 signal markers, only five have any test against the SOA corpus:

| Our marker (post-Phase 0) | SOA enum | SOA lift |
|---|---|---|
| `2024-onwards` | `2024-onwards` | **1.87** |
| `ai-visuals` (was `synthetic-album-art`) | `ai-visuals` | **1.32** |
| `inconsistent-style` | `inconsistent-style` | **1.19** |
| `high-output` | `high-output` | **1.07** |
| `anonymous` (was `anonymous-project`) | `anonymous` | **1.00** |

The other 9 markers — `no-musicbrainz`, `no-physical-release`, `suno-duration-cap`, `popularity-follower-mismatch`, `placeholder-bio`, `gpt-lyric-patterns`, `recent-only-listener-history`, `thin-cross-platform`, `no-live-presence` — are **untested**. Their priority order in `SIGNAL_MARKERS` is the dev plan's prior and will be re-ranked after Phase 2 calibration runs.

### 2. `anonymous` does not discriminate on its own

Lift of **1.001** means flagged at almost identical rates in disclosed-AI (64.0%) and undisclosed (63.9%) entries. The dev plan's claim that `anonymous` is a "dominant marker" is empirically wrong for the SOA corpus — it's dominant in *volume*, not in *signal*.

Combined with high Jaccard co-occurrence with `ai-visuals` (0.648) and `high-output` (0.487), it appears SOA flaggers applied the `ai-visuals` + `anonymous` + `high-output` trio as a package, not as independent observations. Treat these three as **one evidence cluster**, not three independent signals.

### 3. `high-output` is similarly weak alone

Lift 1.07. Co-occurs with `ai-visuals` (Jaccard 0.574) and `anonymous` (0.487). Same cluster-mate story.

### 4. `2024-onwards` is the strongest empirical marker we have

Lift 1.87 — disclosed-AI entries are nearly twice as likely to carry this marker as undisclosed entries. Combined with the temporal logic (AI music tooling reached prosumer accessibility in 2023–2024), this should be the highest-weight marker for which we have empirical support.

### 5. `shScore` is dead

Populated in **0 / 1,375** entries. The SOA schema declared the field; data was never populated. Dev plan's prior is confirmed. Stays out of our rubric.

### 6. TikTok / Instagram are not discriminators

| Platform | All entries | Disclosed-AI |
|---|---|---|
| Spotify | 100.0% | 100.0% |
| YouTube | 93.0% | 97.9% |
| Apple Music | 92.6% | 86.4% |
| Amazon | 77.6% | 69.1% |
| Instagram | 44.4% | 49.2% |
| TikTok | 43.0% | 45.8% |

Spotify is 100% because SOA submissions are gated on Spotify presence — a **sampling artifact**, not a signal. TikTok/Instagram coverage is roughly equal across disclosed-AI vs. all entries, so cross-platform-thinness on those two specifically is *not* an AI signal in this corpus. Surprisingly, **Apple Music and Amazon presence are slightly *lower* in disclosed-AI** — AI artists are over-represented on Spotify but under-represented on the secondary streamers. This contradicts the dev plan's thin-cross-platform assumption *for these specific platforms*. Niche platforms (Bandcamp, MusicBrainz, Discogs) — which SOA doesn't track — may still be useful.

### 7. `disclosureTypes` is a structured field we hadn't planned for

Only 3.7% (51 entries) populate it, but the structure is useful — when populated, it tells you *which aspect* of production used AI:

| Type | Count |
|---|---|
| vocals | 47 |
| instrumentation | 35 |
| mastering | 26 |
| mixing | 26 |
| lyrics | 5 |

Vocals is the most disclosed-about modality. Future schema work could add an optional `ai_modalities` field to our verdict so that high-confidence cases can specify *what* the AI did, not just *whether*.

## Concrete rubric / taxonomy changes (Phase 0 exit criterion ≥ 3)

1. **Renamed `synthetic-album-art` → `ai-visuals`.** Broadens scope beyond album art alone (music videos, profile imagery), and aligns with SOA's enum so the empirical priors apply directly.
2. **Renamed `anonymous-project` → `anonymous`.** SOA enum compatibility.
3. **Reordered `SIGNAL_MARKERS` by empirical lift** where measured. `2024-onwards` first; `anonymous` last among SOA-tested markers; the nine untested markers slotted by dev-plan prior.
4. **Demoted `anonymous` and `high-output` to cluster-mate status.** These three (`ai-visuals` + `anonymous` + `high-output`) are highly redundant — count the *cluster*, not the individual markers, when calibrating confidence. The system prompt and confidence-calibration logic in `rubric.py::SYSTEM_PROMPT` should reflect this in Phase 2.
5. **Dropped `shScore` from any future assumption.** Already noted; data confirms.
6. **Don't weight TikTok/Instagram absence in `thin-cross-platform`.** Their coverage is platform-independent of AI status in SOA. The marker should be defined against niche platforms SOA doesn't track (Bandcamp, MusicBrainz, Discogs).
7. **Don't treat Spotify presence as a positive AI signal.** SOA's 100% Spotify coverage is a sampling artifact; we can't validate the direction. Absence might still be informative, but presence carries no information.

## Calibration set composition

| Tier | Description | Pool size | Sampled | Expected label |
|---|---|---|---|---|
| 1 | `disclosure ∈ {confirmed, full}` | 236 | 50 | `ai` |
| 2 | `disclosure == partial` | 180 | 50 | `likely_ai` |
| 3 | `disclosure == none` and ≥3 markers | 442 | 50 | `likely_ai` |
| 4 | `disclosure == none` and ≤1 marker | 244 | 50 | `unclear` |
| 5 | human controls (manual pick) | — | **0 (pending)** | `human` |

Frozen with `RANDOM_SEED = 20260517` (today's date). Re-running `python analysis/eda.py` against the same SOA snapshot will produce byte-identical output.

**Tier 5 is the remaining manual step.** Populate `analysis/human_controls.json` with 50 entries satisfying: present in MusicBrainz, has Discogs physical release, has concert history (Songkick/Bandsintown), pre-2020 catalog start. Template at `analysis/human_controls.template.json`.

## Acceptance bar for Phase 2

Re-stated from the dev plan, to be evaluated when the agent loop runs against the frozen calibration set:

- ≥85% agreement with tier 1 (gold positives)
- ≥75% agreement with tier 2 (partial disclosure)
- All 50 tier-5 human controls correctly classified `likely_human` or `human`
- Tier 4 (ambiguous) confidence distribution NOT concentrated >0.7 — diagnostic of overconfidence

Record actual numbers here when Phase 2 runs.

## Disclosure distribution snapshot

| Disclosure | Count | % of active |
|---|---|---|
| none | 959 | 69.7% |
| confirmed | 215 | 15.6% |
| partial | 180 | 13.1% |
| full | 21 | 1.5% |

Disclosed-AI total (confirmed + full) = 236 (17.2%) — matches dev plan's 17% estimate.
