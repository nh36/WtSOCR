#!/usr/bin/env python3
"""Freeze exact high-confidence source-compatible final-ṅ candidates."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QA_ROOT = ROOT / "release/current/qa"
FIELDS = [
    "frozen_prepass_sha", "volume", "page", "line", "token_index",
    "tibetan_syllable", "source_token", "target", "candidate_status",
    "alignment_category", "damage_category", "context_excerpt",
]


def read_rows(filename: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(QA_ROOT.glob(f"*/tibetan_cleanup_diagnostics/{filename}")):
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    return rows


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=FIELDS, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def build_frozen_rows(sha: str) -> list[dict[str, str]]:
    candidates = read_rows("tibetan_final_ng_source_compatible_candidates.tsv")
    positional = [
        row
        for row in candidates
        if row["source_compatible_category"]
        == "source_compatible_dominant_consensus"
    ]
    eligible_syllables = {row["tibetan_syllable"] for row in positional}
    withheld = [
        row
        for row in candidates
        if row["source_compatible_category"]
        == "source_compatible_damaged_context"
        and row["tibetan_syllable"] in eligible_syllables
    ]
    targets: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in positional:
        targets[
            (row["tibetan_syllable"], row["source_latin_token"])
        ].add(row["proposed_latin_target"])
    ambiguous = {key: value for key, value in targets.items() if len(value) != 1}
    if ambiguous:
        raise ValueError(f"Ambiguous source-compatible targets: {ambiguous}")

    frozen = [
        {
            "frozen_prepass_sha": sha,
            "volume": row["volume"],
            "page": row["page"],
            "line": row["line"],
            "token_index": row["token_index"],
            "tibetan_syllable": row["tibetan_syllable"],
            "source_token": row["source_latin_token"],
            "target": row["proposed_latin_target"],
            "candidate_status": "positional",
            "alignment_category": row["source_compatible_category"],
            "damage_category": "none",
            "context_excerpt": row["context_excerpt"],
        }
        for row in positional
    ]
    frozen.extend(
        {
            "frozen_prepass_sha": sha,
            "volume": row["volume"],
            "page": row["page"],
            "line": row["line"],
            "token_index": row["token_index"],
            "tibetan_syllable": row["tibetan_syllable"],
            "source_token": row["source_latin_token"],
            "target": row["proposed_latin_target"],
            "candidate_status": "withheld_damage",
            "alignment_category": row["source_compatible_category"],
            "damage_category": row["damage_scope"],
            "context_excerpt": row["context_excerpt"],
        }
        for row in withheld
    )
    for row in read_rows("tibetan_final_ng_same_entry_echo_candidates.tsv"):
        key = (row["tibetan_syllable"], row["additional_source_token"])
        if key not in targets:
            continue
        target = next(iter(targets[key]))
        frozen.append(
            {
                "frozen_prepass_sha": sha,
                "volume": row["volume"],
                "page": row["page"],
                "line": row["line"],
                "token_index": row["token_index"],
                "tibetan_syllable": row["tibetan_syllable"],
                "source_token": row["additional_source_token"],
                "target": target,
                "candidate_status": "echo",
                "alignment_category": row["echo_category"],
                "damage_category": (
                    row["echo_category"]
                    if row["echo_category"]
                    in {"damaged_reference", "marker_attached"}
                    else "none"
                ),
                "context_excerpt": row["context_excerpt"],
            }
        )
    return sorted(
        frozen,
        key=lambda row: (
            row["tibetan_syllable"],
            row["source_token"],
            row["candidate_status"],
            row["volume"],
            int(row["page"]),
            int(row["line"]),
            int(row["token_index"]),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = build_frozen_rows(args.sha)
    write_rows(args.output, rows)
    positional = sum(row["candidate_status"] == "positional" for row in rows)
    withheld = sum(row["candidate_status"] == "withheld_damage" for row in rows)
    echoes = sum(row["candidate_status"] == "echo" for row in rows)
    print(
        f"positional={positional} withheld_damage={withheld} "
        f"echoes={echoes} total={len(rows)}"
    )


if __name__ == "__main__":
    main()
