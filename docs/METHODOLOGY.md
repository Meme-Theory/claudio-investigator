# Methodology

> **Status:** Draft skeleton. Public-facing version lands in Phase 4 once the rubric has run against a calibration set and we have real numbers to report. This file is intentionally honest about what is and isn't decided.

## What ClAudio Investigator does

Given an artist name, ClAudio Investigator runs a Claude Haiku 4.5 agent that queries free public music APIs (iTunes, Spotify, YouTube, MusicBrainz, Discogs, Deezer, Last.fm, Genius), gathers metadata signals, and renders a structured verdict on whether the artist appears to be AI-generated, human, or somewhere in between.

The verdict is one of five values: `ai`, `likely_ai`, `unclear`, `likely_human`, `human`. Each verdict has an attached confidence (0.0–1.0), a list of signal markers, an evidence trail, and a short written reasoning. All of that lands as a JSON file at `src/{slug}.json` and as a comment on the originating GitHub issue.

## What it does *not* do

- **It does not analyze audio.** This is metadata fingerprinting only. Audio classification is deferred to a possible Phase 5; we want to see how far metadata alone can go.
- **It does not accuse individual humans.** Verdicts are about projects and catalogs, not about people. A project can be AI-generated regardless of whether one specific track involved human creative work.
- **It does not produce a binary "is AI" judgment.** The five-value scale exists because the truth is genuinely a spectrum — human/AI collaboration is a real category, not a copout.

## How the agent reasons

The agent has access to a fixed set of tools, one per API source plus a vision tool for album-art analysis. It picks which tools to call and in what order — there's no fixed pipeline. The constraints are:

- The system prompt, in `investigator/rubric.py`. This tells the agent what signals matter and how to calibrate confidence.
- A budget cap of 12 iterations, 20k tokens, $0.50 per investigation. Most investigations land at $0.03–0.10.
- The signal taxonomy in `docs/SIGNALS.md`, which the agent must use when flagging markers.

## Confidence calibration

| Confidence | Interpretation | What happens |
|---|---|---|
| ≥ 0.90 | Multiple strong, independent signals; no contradiction | PR auto-opened to `src/` |
| 0.70–0.90 | Strong but with some ambiguity | Auto-merge only if ≥ 3 markers, else `needs-review` |
| 0.50–0.70 | Mixed signals | Labeled `needs-review`, no PR |
| < 0.50 | Insufficient evidence | Labeled `low-confidence`, comment only |

These thresholds will be re-tuned once Phase 0 EDA data + Phase 2 calibration results land.

## Re-investigation

Entries are re-investigated quarterly. Verdicts can shift over time — an artist who initially looked AI-generated may accumulate Discogs entries, live performance history, or a clear human attribution, and get demoted from `likely_ai` to `unclear` or `likely_human`. The inverse is rarer but possible (an artist deletes their socials and live history disappears).

The full investigation history is preserved in the entry's revision history; the *current* verdict is what `src/{slug}.json` shows.

## Removal requests

Artists or rights-holders who believe their entry is wrong can open a removal-request issue (Phase 4). The flow is:
1. The originating verdict is re-run with a fresh investigation.
2. If the new verdict drops below `likely_ai`, the entry is removed.
3. If it remains `ai` / `likely_ai` with high confidence and contradicting evidence is not produced, the entry stands.

## Sources of error

- **Tool absence ≠ ground truth absence.** Free-tier APIs miss things. An artist could be on MusicBrainz under a different spelling or have a Discogs entry indexed late.
- **Pattern overfitting.** The signal taxonomy was developed against the Soul Over AI corpus, which has its own selection biases. We mitigate by re-investigating quarterly and by treating community-flagged data as lower-confidence than disclosure-confirmed data.
- **Model drift.** Verdicts depend on the Claude model. We pin the model version in each record (`model: "claude-haiku-4-5-20251001"`) so a verdict can be re-run on the same model later for a clean compare.

## Reproducibility

Every verdict captures the inputs the agent saw and the tool calls it made (Phase 4 will surface this in the issue comment). The investigation can be replayed against the same model + tools and should produce a closely-matching verdict, modulo platform data drift between runs.

## License

- **Source code** is MIT-licensed (see `LICENSE`).
- **The curated artist index** (`src/`, `dist/artists.json`) is licensed under the Open Database License (ODbL) v1.0, with individual record contents under the Database Contents License (DbCL) v1.0 (see `LICENSE-data`).

Downstream uses of the database must include the ODbL attribution string and share derived databases under ODbL.
