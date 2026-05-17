# Fixtures

Canned API responses used by `tests/test_tools.py`. Each file is **hand-crafted**
to match the documented response shape of the corresponding API — they are NOT
verbatim captures from production. Replace them with real captures once you
have keys configured:

```bash
# iTunes (no auth)
curl 'https://itunes.apple.com/search?term=aphex+twin&entity=musicArtist&country=us&limit=5' \
  > tests/fixtures/itunes_search_known_human.json

# MusicBrainz (UA required)
curl -H "User-Agent: ClAudioInvestigator/0.0.1 (https://github.com/Meme-Theory/claudio-investigator)" \
  'https://musicbrainz.org/ws/2/artist?query=aphex+twin&fmt=json&limit=10' \
  > tests/fixtures/musicbrainz_found.json
```

Naming convention: `{source}_{scenario}.json`. Scenarios cover both the happy
path (artist found, populated) and absence (no results / no match) — tools must
handle both cleanly because absence is a first-class signal.
