# Data directory

This beta package includes `corpus_profile.json`, a compiled style profile generated from the supplied rap corpus. It does **not** need the raw RTF or full raw lyric corpus to run.

For a private deployment that builds the profile from raw lyrics, keep the raw file outside your public repository and set `NMC_CORPUS_PATH=/secure/path/to/rap_corpus.txt`. For public beta deployment, prefer the compiled profile path:

```text
NMC_PROFILE_PATH=data/corpus_profile.json
NMC_EXPOSE_CORPUS_SAMPLES=0
```


## Comparison profiles

`comparison_profiles.json` contains derived benchmark statistics from the uploaded rapper-comparison data. It intentionally excludes raw commercial lyrics and line samples. The app uses it for similarity scoring, cadence targets, rhyme entropy, internal-rhyme density, and line-level benchmark advice.

For rebuilding these profiles from private source material, keep the raw file outside the public repository and set `NMC_COMPARISON_PROFILE_PATH` to a generated profile JSON.
