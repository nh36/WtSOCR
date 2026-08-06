#!/usr/bin/env python3
"""Validate exact final-ṅ corrections against genuine final-n controls."""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from postprocess_entry_map import extract_alternate_witness_tokens


REGISTRY = ROOT / "data/final_ng_source_token_collision_controls.tsv"
OVERRIDES = ROOT / "data/reviewed_tibetan_exact_overrides.tsv"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def release_lines(root: Path) -> dict[tuple[str, int, int], str]:
    result: dict[tuple[str, int, int], str] = {}
    for path in (root / "release/current/qa").glob("wts_*/*_line_zones.tsv"):
        volume = path.parent.name
        for row in read_tsv(path):
            result[(volume, int(row["page"]), int(row["line"]))] = row["line_text"]
    return result


def validate(root: Path = ROOT) -> list[str]:
    controls = read_tsv(root / REGISTRY.relative_to(ROOT))
    overrides = read_tsv(root / OVERRIDES.relative_to(ROOT))
    lines = release_lines(root)
    errors: list[str] = []
    controls_by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    override_keys = {
        (
            row["volume"],
            int(row["page"]),
            int(row["line"]),
            int(row["token_index"]),
            row["from_token"],
            row["to_token"],
        )
        for row in overrides
    }
    for row in controls:
        controls_by_source[row["source_latin_token"]].append(row)
        key = (row["volume"], int(row["page"]), int(row["line"]))
        current = lines.get(key)
        if current is None:
            errors.append(f"{key}: collision control line is missing")
            continue
        if row["tibetan_syllable"] not in current:
            errors.append(f"{key}: Tibetan control syllable is missing")
        registered_excerpt = row["expected_complete_line_excerpt"]
        corrected_excerpt = registered_excerpt.replace(
            row["source_latin_token"], row["expected_latin_form"]
        )
        if registered_excerpt not in current and corrected_excerpt not in current:
            errors.append(f"{key}: complete-line control excerpt no longer matches")
        tokens = [token for token, _start, _end in extract_alternate_witness_tokens(current)]
        index = int(row["token_index"])
        expected = row["expected_latin_form"]
        if row["polarity"] == "positive" and (
            row["volume"],
            int(row["page"]),
            int(row["line"]),
            index,
            row["source_latin_token"],
            row["expected_latin_form"],
        ) not in override_keys:
            expected = row["source_latin_token"]
        if index > len(tokens) or tokens[index - 1] != expected:
            errors.append(
                f"{key} token {index}: expected {expected!r}, "
                f"found {tokens[index - 1] if index <= len(tokens) else '<missing>'!r}"
            )

    for row in overrides:
        source = row["from_token"]
        if source not in controls_by_source:
            continue
        key = (row["volume"], int(row["page"]), int(row["line"]))
        current = lines.get(key, "")
        negative_syllables = {
            control["tibetan_syllable"]
            for control in controls_by_source[source]
            if control["polarity"] == "negative"
        }
        positive_syllables = {
            control["tibetan_syllable"]
            for control in controls_by_source[source]
            if control["polarity"] == "positive"
            and control["expected_latin_form"] == row["to_token"]
        }
        if (
            any(syllable in current for syllable in negative_syllables)
            and not any(syllable in current for syllable in positive_syllables)
        ):
            errors.append(f"{key}: exact {source} override targets a known final-n syllable")
        if row["to_token"] == source:
            errors.append(f"{key}: no-op collision override is not permitted")

    return errors


def main() -> None:
    errors = validate()
    if errors:
        raise SystemExit("\n".join(errors))
    print("Final-ng source-token collision controls passed.")


if __name__ == "__main__":
    main()
