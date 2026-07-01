#!/usr/bin/env python3
"""Build derived rapper comparison profiles without storing raw lyrics.

Manifest format:
{
  "profiles": [
    {
      "id": "artist_example",
      "name": "Artist-style benchmark",
      "artist_family": "Artist family",
      "source_label": "private reference set",
      "path": "/secure/private/artist_reference.txt",
      "notes": ["short note"],
      "benchmark_moves": ["coaching move"]
    }
  ]
}

The output JSON contains only statistical fingerprints: cadence histograms,
rhyme-key distributions, entropy, line-length targets, and coaching metadata.
It does not include raw lyric lines.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lyric_engine import build_line_details  # noqa: E402
from comparison_engine import _stats_from_details  # noqa: E402


def _profile_from_text(spec: Dict[str, Any], base_dir: Path) -> Dict[str, Any]:
    source_path = Path(str(spec.get("path") or "")).expanduser()
    if not source_path.is_absolute():
        source_path = base_dir / source_path
    raw = source_path.read_text(encoding="utf-8", errors="replace")
    details = build_line_details(raw)
    stats = _stats_from_details(details, raw)
    cadence_histogram = stats.pop("cadence_histogram", [])
    word_count_histogram = stats.pop("word_count_histogram", [])
    top_rhyme_keys = stats.pop("top_rhyme_keys", [])
    q = stats.get("syllable_q1_median_q3") or [8, 12, 16]
    wq = stats.get("word_count_q1_median_q3") or [6, 9, 12]
    return {
        "id": spec.get("id") or source_path.stem,
        "name": spec.get("name") or f"{source_path.stem} benchmark",
        "artist_family": spec.get("artist_family") or spec.get("name") or source_path.stem,
        "source_label": spec.get("source_label") or "private reference text",
        "content_policy": "derived_profile_only_no_raw_lyrics",
        "notes": list(spec.get("notes") or []),
        "stats": stats,
        "cadence_histogram": cadence_histogram,
        "word_count_histogram": word_count_histogram,
        "top_rhyme_keys": top_rhyme_keys[:14],
        "benchmark_moves": list(spec.get("benchmark_moves") or []),
        "line_targets": {
            "one_bar_syllables": [q[0], q[-1]] if isinstance(q, list) and len(q) >= 2 else [8, 16],
            "median_line_syllables": stats.get("median_syllables", 0),
            "median_line_words": stats.get("median_words", 0),
            "word_window": [wq[0], wq[-1]] if isinstance(wq, list) and len(wq) >= 2 else [6, 12],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build derived comparison_profiles.json from private lyric text files.")
    parser.add_argument("--manifest", required=True, help="JSON manifest describing private source files.")
    parser.add_argument("--output", default="data/comparison_profiles.json", help="Destination JSON path.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8", errors="replace"))
    base_dir = manifest_path.parent
    profiles: List[Dict[str, Any]] = []
    for spec in manifest.get("profiles", []):
        profiles.append(_profile_from_text(spec, base_dir))

    data = {
        "metadata": {
            "version": "custom-comparison-profile",
            "generated_from": "private_manifest",
            "copyright_handling": "raw lyrics are not bundled; output contains derived statistical profiles only",
            "profile_count": len(profiles),
            "available_reference_ids": [p.get("id") for p in profiles],
            "feature_notes": [
                "Scores are similarity benchmarks, not imitation instructions.",
                "No lyric lines from reference artists are stored in this JSON.",
                "Use profiles to guide bar length, internal-rhyme density, hook clarity, entropy, and rhyme-family variety.",
            ],
        },
        "profiles": profiles,
    }
    output_path = Path(args.output).expanduser()
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(profiles)} derived profiles to {output_path}")


if __name__ == "__main__":
    main()
