# 🧞 ITTY BITTY LIVING SPACE

> **Status:** Stashed for the next arms-race round, not for today. Drafted 2026-05-18 by the project owner. Implement when current-generation Suno/Udio output starts beating the existing rubric on the joint distribution and we need to harden against adversarial cleanup.

Five-fact eval rubric, weighted for current-generation Suno/Udio output. Each fact returns a signal score; weighted sum + threshold yields verdict. Designed so individual facts can flip even when others look clean — AI acts can fake any single signal but struggle to fake the joint distribution.

**1. Temporal footprint** *(weight: high)*
First release date vs. catalog depth vs. live performance history. Pure-AI acts overwhelmingly first-appear 2023-onwards with zero pre-2023 footprint and zero documented live shows. Pull: earliest release timestamp across all DSPs, count of dated live performances on Bandsintown/Songkick/setlist.fm, archive.org snapshots of any artist page predating first release. Red flag: >50 tracks released, zero shows, first appearance post-Jan 2024. Green flag: any verifiable live show, any pre-2023 release, any archive.org capture of the artist page from before audio existed.

**2. Identity persistence** *(weight: high)*
Named, photographed, cross-referenceable humans. Real bands have members who appear in multiple contexts — interviews, other bands, label rosters, social media tagging, photo metadata. Pull: count of named individuals in bios/interviews, count of those names appearing in other verifiable musical contexts, presence of EXIF-bearing photos showing humans, cross-band membership (the Spinning Coin / Hairband pattern from the validation set). Red flag: no named members, or names that exist nowhere else on the indexable web. Green flag: a member of the act is verifiably a member of a different act, or has a non-music professional footprint.

**3. Output velocity vs. production complexity** *(weight: medium-high)*
Releases-per-month against per-track production cost. Real acts release roughly in inverse proportion to arrangement complexity — a solo bedroom act can drop a track weekly, a seven-piece with horn arrangements cannot. AI inverts this: full-band-sounding acts dropping multi-track albums weekly is a strong tell. Pull: release calendar density, instrument count per track (Claude can estimate from audio), feature credits per release. Red flag: orchestral or full-band arrangements at >2 releases/month with no session musician credits. Green flag: cadence matches arrangement scale, or genre is one humans actually do produce at high velocity (solo ambient, beat tapes, harsh noise).

**4. Distribution and metadata fingerprint** *(weight: medium)*
Distributor, label network, and ISRC patterns. AI acts cluster heavily on DistroKid/CD Baby/TuneCore self-release pipelines with no label, no PRO registration, no publisher, and ISRC blocks issued in tight batches. Real obscure acts more often route through a small label (even if it's just one friend's Bandcamp imprint), have BMI/ASCAP/PRS registrations, and have ISRCs scattered across years. Pull: distributor from Spotify metadata, label field, ISRC prefix analysis, PRO database hits. Red flag: pure self-distribution, no PRO, ISRC batch from same week as artist creation. Green flag: any label affiliation with other roster artists, any PRO registration, scattered ISRC issuance dates.

**5. Bio and visual asset linguistics** *(weight: medium, asymmetric)*
Text and image artifacts in artist-controlled surfaces. AI acts disproportionately use specific bio-language patterns ("blending human creativity with AI", "modern AI tools", "the future of music", "creative engine") — Soul Over AI's notes field is full of these. Visual side: cover art with AI-generation artifacts (hand mangling, text gibberish, soft-focus stylistic drift across releases), inconsistent member depictions across covers, no candid/non-promotional photos anywhere. Pull: bio text from Spotify/YouTube/Apple/Bandcamp, cover art across releases, social media imagery. Red flag: any explicit AI-tooling language in bio, OR cover-art generation artifacts on >2 releases. Green flag: bio mentions specific gear/studio/producer by name, candid photos exist.

---

**Aggregation:**
Weighted score = 3·(temporal) + 3·(identity) + 2·(velocity) + 2·(distribution) + 2·(linguistic), each fact returning −1 (green), 0 (ambiguous), or +1 (red). Range −12 to +12. Threshold +4 = AI verdict, −4 = human verdict, between = needs human review. Crucial: temporal OR identity alone scoring +1 should not exceed threshold by itself — joint distribution is the discriminator, not any single axis. Skyebrows in your validation set would fail single-axis tests (real CG-industry person with public footprint) but join-distribution-fail on linguistic + visual.

**Adversarial decay note:** facts 1, 2, and 4 are robust to better generators because they're not about the audio. Facts 3 and 5 erode as generators improve. When Mythos rolls out, the audio-side facts get reinforced — spectrogram artifacts, vocoder fingerprints, training-set memorization probes — and the meta-data facts stay as belt-and-suspenders. The detection ceiling isn't audio quality; it's whether the act exists as a social object outside the audio files.
