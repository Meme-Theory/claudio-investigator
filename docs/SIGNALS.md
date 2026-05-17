# Signal Taxonomy

The canonical marker list lives in `investigator/rubric.py` as `SIGNAL_MARKERS`. This document explains what each marker means, why it's a signal, and how to evidence it. If this file and `rubric.py` disagree, **`rubric.py` wins** — update this doc, not the code.

A marker is only flagged when the agent has direct evidence for it. Absence-as-evidence (e.g. no MusicBrainz entry) counts; speculation does not.

The order in `SIGNAL_MARKERS` reflects empirical Phase 0 priors against the Soul Over AI corpus where the marker was testable, and dev-plan priors otherwise. Five markers carry SOA-measured lift ratios; nine are untested in SOA and await Phase 2 calibration data. See `CALIBRATION_NOTES.md` for the lift table.

## Catalog & ground-truth markers

### `no-musicbrainz`
**What:** Artist has no MusicBrainz entry under their stage name or any obvious alias.
**Why it's a signal:** MusicBrainz is community-curated and has near-universal coverage of human artists with any recorded output. AI music projects are systematically missing — nobody bothers entering them. Absence is one of the strongest single tells.
**Evidence shape:** `lookup_musicbrainz` returns `{found: false}` for the canonical name and all submitter-provided aliases.
**Caveats:** New human artists (debut <12 months) may also be missing. Don't weight as heavily if catalog is genuinely new in a way that matches a human debut pattern (one EP, one venue, social presence).

### `no-physical-release`
**What:** No Discogs entry for any physical media — no vinyl, CD, cassette, or release-by-label.
**Why it's a signal:** Pressing physical media costs money and requires a label or distributor relationship. AI music projects almost never bother. For an artist with significant streaming presence, complete absence from Discogs is suspicious.
**Caveats:** Genre-dependent — purely-digital electronic / bedroom-pop artists can legitimately have no physical releases. Weight low if catalog is small.

### `2024-onwards`
**What:** The entire discoverable catalog dates from 2024 or later, with no earlier release, social, or press footprint.
**Why it's a signal:** AI music tooling reached prosumer accessibility in 2023–2024. A "complete artist" with no pre-2024 trace at any platform is the modal AI artist shape.
**Caveats:** Real new artists exist. Pair with at least one other marker before weighting heavily.

## Release-pattern markers

### `high-output`
**What:** More than 12 releases in any 12-month window, with no historical baseline at that velocity.
**Why it's a signal:** Generative music projects can ship a track a week; human projects can't sustain that.
**Caveats:** Some real artists (beatmakers, prolific producers) legitimately hit this. Combine with absence signals.
**Phase 0 caveat:** SOA lift = 1.07 — weak discriminator on its own. Co-occurs heavily with `ai-visuals` (Jaccard 0.57) and `anonymous` (Jaccard 0.49). Treat as cluster-mate, not as a primary signal in isolation.

### `suno-duration-cap`
**What:** Track durations cluster suspiciously around 2:00–2:30.
**Why it's a signal:** Suno's free tier caps at ~2 minutes per generation. Artists whose entire catalog hugs that cap are very often Suno-generated.
**Caveats:** Genre conventions (punk, grindcore) legitimately produce short tracks. Look for cluster *shape*, not just duration.

### `recent-only-listener-history`
**What:** Last.fm listener curve is a step function (long flat zero, sudden jump, flat at new level) rather than an organic growth curve.
**Why it's a signal:** Real artist discovery is gradual. Step functions indicate algorithmic placement or batch-bot activity.

## Cross-platform presence markers

### `thin-cross-platform`
**What:** Present on the major streaming services but absent from niche or community platforms (Bandcamp, Discogs, Soundcloud non-zero, scene-specific aggregators).
**Why it's a signal:** Real artists historically scatter — they had a Bandcamp before they had a Spotify, they tagged a SoundCloud, they got blogged about somewhere. Catalog presence with no community presence reads as distributor-only delivery.

### `anonymous`
**What:** No individual humans named or linked anywhere — no writer credits, no producer credits, no socials, no interviews, no photos that aren't AI-generated.
**Why it's a signal:** Real anonymity is rare and conspicuous (e.g. SBTRKT, Daft Punk pre-reveal). Casual anonymity (no profile at all) reads as AI.
**Phase 0 caveat:** SOA lift = 1.001 — this marker does NOT discriminate disclosed-AI from undisclosed entries *on its own* in the SOA corpus. It also co-occurs heavily with `ai-visuals` (Jaccard 0.65) and `high-output` (Jaccard 0.49), suggesting SOA flaggers applied the trio as a package. Treat as a cluster-mate of `ai-visuals`; do not weight it independently for high-confidence verdicts.
**Note:** This was `anonymous-project` pre-Phase 0; renamed to match SOA's enum.

### `no-live-presence`
**What:** Zero concert listings (Songkick, Bandsintown), no venue tagging on socials, no tour history.
**Why it's a signal:** Live performance is the floor of being a real act. Total absence is consistent with non-corporeality.

## Content markers

### `placeholder-bio`
**What:** Bio is missing, AI-generated text patterns, generic template phrasing, or auto-translated obvious slop.
**Why it's a signal:** Real artists or their teams write bios with specifics (where they're from, what they sound like, who they've worked with). Generic-template bios are a tell.

### `ai-visuals`
**What:** AI-generation fingerprints in any visual asset associated with the artist — album art, music videos, profile imagery. Banding artifacts, hand malformations, signature compositional patterns of Midjourney/SD/etc.
**Why it's a signal:** Self-explanatory. In the SOA corpus this was the second-highest-lift marker (1.32) and the highest-volume one (flagged on 73% of all active entries, 91% of disclosed-AI).
**Cost:** Most expensive signal to collect (vision pass on album art). Use the vision tool only when cheaper signals are ambiguous.
**Note:** This was `synthetic-album-art` pre-Phase 0; renamed to match SOA's enum and broaden scope beyond album art alone.

### `gpt-lyric-patterns`
**What:** Lyrics show LLM tells — semantic loops, characteristic rhyme dependencies (the "rhymes of ChatGPT"), filler phrasing where real lyrics would be specific.
**Why it's a signal:** Self-explanatory.
**Method:** Pull lyrics from Genius, analyze with the agent — don't outsource detection to a classifier.

## Coherence markers

### `popularity-follower-mismatch`
**What:** Spotify popularity (0–100) is high relative to follower count by >1 standard deviation against the population.
**Why it's a signal:** Real artists' followers and popularity correlate — popularity rises *because* followers stream. AI artists often get high popularity from playlist placement with no follower base — the metrics decouple.
**Method:** Compare against a benchmark distribution maintained outside this doc (Phase 4).

### `inconsistent-style`
**What:** Wild genre swings across the catalog (folk → trap → orchestral → metal in 18 months) with no curatorial framing.
**Why it's a signal:** Real artists explore but coherently. Catalogs that read as a tool demo (one of each genre) read as one.

---

## Adding new markers

A marker earns inclusion when it passes:
1. **Lift > 2× in the Soul Over AI corpus** (or equivalent labeled set) — present in confirmed-AI entries at least twice as often as in human controls.
2. **At least one cheap-to-collect path** — must be derivable from one or two tool calls.
3. **Independence from existing markers** — co-occurrence with any existing marker must be <0.7 in the corpus. If it correlates higher than that, you're adding redundancy, not coverage.

Promoting a draft marker to canonical means: add it to `SIGNAL_MARKERS` in `rubric.py`, mirror it here, and re-run the calibration set to verify no regression on existing tiers.

## Dropped from consideration

- `submithub-low-score` — SOA tracked it; the field was never populated. Not enough data to validate.
- `spotify-audio-features-anomaly` — endpoint deprecated for new apps in Nov 2024.
