#!/usr/bin/env python3
"""Record one exact Tibetan-syllable transcription-integrity family."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_tibetan_latin_integrity.py"
SPEC = importlib.util.spec_from_file_location("tibetan_latin_integrity", SCRIPT)
assert SPEC and SPEC.loader
integrity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = integrity
SPEC.loader.exec_module(integrity)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tibetan", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    sources = set(args.sources.split(","))
    aligned = integrity.collect_all_aligned(ROOT / "release/current")
    diagnostics = integrity.build_diagnostics(ROOT / "release/current")
    by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in diagnostics
    }
    selected: list[dict[str, str]] = []
    for row in aligned:
        if (
            row["tibetan_syllable"] != args.tibetan
            or row["latin_token"] not in sources
        ):
            continue
        key = (row["volume"], row["page"], row["line"], row["token_index"])
        diagnostic = by_key[key]
        if diagnostic["alignment_confidence"] not in {
            "secure_positional_alignment", "secure_reviewed_alignment",
        }:
            continue
        if row["damage_scope"] not in {"none", "later_gloss_or_commentary"}:
            continue
        if row["marker_attached"] == "yes":
            continue
        selected.append(row)
    if not selected:
        raise ValueError("No secure exact identities selected")
    path = integrity.OVERRIDES_PATH
    rows = integrity.read_tsv(path)
    fields = list(rows[0])
    existing = {
        (r["volume"], r["page"], r["line"], r["token_index"], r["from_token"])
        for r in rows
    }
    for row in selected:
        key = (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["latin_token"],
        )
        if key in existing:
            raise ValueError(f"Exact identity already reviewed: {key}")
        rows.append({
            "volume": row["volume"], "page": row["page"],
            "line": row["line"], "token_index": row["token_index"],
            "from_token": row["latin_token"], "to_token": args.target,
            "reason": "reviewed_tibetan_exact_transcription_integrity",
            "evidence": args.evidence,
            "review_note": (
                f"Exact {args.tibetan} alignment; reviewed root-feature repair "
                "and canonical full target; no Latin-wide substitution."
            ),
        })
    rows.sort(key=lambda r: (
        r["volume"], int(r["page"]), int(r["line"]),
        int(r["token_index"]), r["from_token"],
    ))
    integrity.write_tsv(path, rows, fields)
    print(f"recorded={len(selected)}")


if __name__ == "__main__":
    main()
