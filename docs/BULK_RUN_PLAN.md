# Bulk SOA Investigation Plan

**Status:** Drafted 2026-05-18.
**Execution window:** June 1, 2026 (when $200/month Anthropic credits land).
**Scope:** Run the agent against every artist in the Soul Over AI public index
(1,378 entries as of clone, 2026-05-18) and seed `data/investigations.jsonl`.

## Cost

Empirical per-investigation cost from prior testing: **~$0.04** (68 API requests
totaling 875K input + 32K output tokens at $0.65 actual spend — ~37% below the
no-cache rate, consistent with system-prompt + tool-schema cache hits).

| Scenario                                  | Cost |
| ----------------------------------------- | ---- |
| 1,378 × $0.04 (empirical, steady-state)   | **~$55** |
| + 30% margin for prod-tuned rubric        | **~$72** |
| Hard upper bound (every run hits $0.50 kill) | $689 |

Single full run fits inside one month's $200 credit with ~3× headroom.
Batch API's 50% discount does **not** apply — the investigator is interactive
tool-use, not single-shot.

Verified rates (Haiku 4.5, 2026):

- Input: $1.00 / MT
- Output: $5.00 / MT
- Cache write (5m): $1.25 / MT
- Cache read: $0.10 / MT

## Mechanism

A local script: `scripts/bulk_investigate.py`. ~15 lines core loop —
read the vendored SOA index, skip artists already in the ledger (case-
insensitive normalized match), call `python -m investigator.main investigate`
per remaining name, append the verdict to `data/investigations.jsonl` using
the same dedup logic the workflow does.

No GitHub Actions matrix, no artifact passing — this runs once, from the
user's machine, against the user's `ANTHROPIC_API_KEY`. The existing
`manual-investigate.yml` workflow stays as-is for ad-hoc one-offs.

**Wall time** — serial: ~45–60s per investigation × 1,378 = ~17–23h.
Plenty of room to run overnight, or add a 4-way `concurrent.futures` pool
in the script after the smoke test confirms rate-limit headroom.

**Resumability** — re-running the script picks up where the previous run
left off because the ledger is the dedup checkpoint. No state file needed.

**Failure handling** — agent already returns `verdict=null` on budget
exhaustion / API errors, which our workflow's ledger guard skips. Same
behavior in the script: only rows with a real verdict get appended.

## Phases

### Phase A — Pre-flight (May, before credits)

- [ ] Vendor SOA index under `analysis/soul-over-ai/` (per dev-plan memo).
      Frozen snapshot; the source list must not move under us mid-run.
- [ ] Write `scripts/bulk_investigate.py`.
- [ ] Smoke test: 10 random SOA artists. Verify ledger ends up clean
      (no duplicates, no null-verdict rows, dedup against prior ledger
      entries works).

### Phase B — Pricing validation (May)

- [ ] Run the script against a **50-artist sample**. Measure:
      real cost-per-investigation, p50/p95 wall time, any Anthropic
      TPM throttling.
- [ ] If median cost > $0.05, pause and re-tune before the full run.
      Update CLAUDE.md cost line with empirical numbers.

### Phase C — Full bulk run (June 1+)

- [ ] Run `bulk_investigate.py` with the full vendored SOA list.
- [ ] Watch first 50 verdicts; abort if per-investigation cost > $0.10
      (signals rubric regression).

### Phase D — Analysis (June)

- [ ] Agreement matrix: our verdict × SOA disclosure label. Save as
      `analysis/soa_agreement_matrix.json`.
- [ ] Triage disagreements: `likely_human|human` from us where SOA flagged
      AI = calibration miss; the inverse = potential new finds.
- [ ] PR generation for confidence ≥ 0.90 verdicts → `src/{slug}.json` is
      **blocked on dev-plan Phase 3** (`investigate-from-issue` is currently
      `NotImplementedError`). Land that first or stage PRs by hand.

## Open questions

1. **Anthropic per-org TPM at the $200-credit tier** — Phase B will surface
   this empirically. If we need concurrency for time, the script grows a
   thread pool; if we get throttled, drop back to serial.
2. **SOA name → ledger normalization** — script must use the same
   `lowercase + collapse-whitespace + strip` key the workflow uses.

## Out of scope

- Updating `src/{slug}.json` directly — dev-plan Phase 3 work.
- Vision passes (`analyze_album_art`) — dev-plan Phase 4.
- Audio classifier — dev-plan Phase 5.
- Re-investigating non-SOA artists submitted via the Phase 3 issue flow once
  it ships — orthogonal to this bulk run.
