#!/usr/bin/env python3
"""Freeze manually approved historical-witness final-ṅ families."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QA_ROOT = ROOT / "release/current/qa"
BASELINE = "6322c7255cfba2fcfaf678cec656e65496ed5f12"
HISTORICAL_FAMILIES = {
    "དྲང": ("dran", "draṅ", "explicit_same_entry_repetition"),
    "ཁོང": ("khon", "khoṅ", "explicit_same_entry_repetition"),
    "ཏིང": (
        "tin", "tiṅ",
        "explicit_same_entry_repetition;direct_repeated_tibetan_alignment",
    ),
    "སྲོང": ("sron", "sroṅ", "explicit_same_entry_repetition"),
    "ཞང": ("Zan", "Zaṅ", "explicit_same_entry_repetition"),
}
REPEATED_POSITION_FAMILIES = {
    "སློང": ("slon", "sloṅ", "repeated_exact_positions_historical_target"),
    "གཏང": ("gtan", "gtaṅ", "repeated_exact_positions_historical_target"),
    "དགུང": ("dgun", "dguṅ", "repeated_exact_positions_historical_target"),
    "སྒོང": ("sgon", "sgoṅ", "repeated_exact_positions_historical_target"),
    "གྱོང": ("gyon", "gyoṅ", "repeated_exact_positions_historical_target"),
    "རུང": ("run", "ruṅ", "repeated_exact_positions_historical_target"),
}
FIELDS = [
    "frozen_prepass_sha", "historical_baseline_sha", "volume", "page",
    "line", "token_index", "tibetan_syllable", "source_token", "target",
    "candidate_status", "alignment_category", "damage_category",
    "historical_anchor_identity", "historical_anchor_provenance_class",
    "family_identity_evidence", "row_local_review_result", "context_excerpt",
]


def read_rows(filename: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(QA_ROOT.glob(f"*/tibetan_cleanup_diagnostics/{filename}")):
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    return rows


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--tier",
        choices=("historical", "repeated-position"),
        default="historical",
    )
    args = parser.parse_args()
    families = (
        REPEATED_POSITION_FAMILIES
        if args.tier == "repeated-position"
        else HISTORICAL_FAMILIES
    )
    candidates = read_rows("tibetan_final_ng_source_compatible_candidates.tsv")
    echoes = read_rows("tibetan_final_ng_same_entry_echo_candidates.tsv")
    historical = read_tsv(ROOT / "data/final_ng_historical_witness_audit.tsv")
    frozen: list[dict[str, str]] = []
    for syllable, (source, target, identity_evidence) in families.items():
        anchors = [
            row for row in historical
            if row["tibetan_syllable"] == syllable
            and row["source_variant"] == source
            and row["target"] == target
            and row["historical_anchor_present"] == "yes"
            and row["historical_baseline_sha"] == BASELINE
            and row.get("transcription_gateway_status") == "pass"
        ]
        if not anchors:
            raise ValueError(
                f"{syllable}: no transcription-integrity-passing "
                "historical witness"
            )
        anchor = anchors[0]
        anchor_identity = (
            f"{anchor['historical_volume']}:{anchor['historical_page']}:"
            f"{anchor['historical_line']}:{anchor['historical_token_index']}:"
            f"{target}"
        )
        family_rows = [
            row for row in candidates
            if row["tibetan_syllable"] == syllable
            and row["source_latin_token"] == source
            and row["proposed_latin_target"] == target
        ]
        if not family_rows:
            raise ValueError(f"{syllable}: no current candidates")
        clean_rows = [
            row for row in family_rows
            if row["source_compatible_category"]
            == "source_compatible_single_anchor"
        ]
        if args.tier == "repeated-position" and len(clean_rows) < 3:
            raise ValueError(
                f"{syllable}: repeated-position tier requires at least "
                f"three clean identities, found {len(clean_rows)}"
            )
        for row in family_rows:
            withheld = row["source_compatible_category"] in {
                "source_compatible_damaged_context",
                "source_compatible_marker_attached",
                "source_compatible_not_final_ng_only",
            }
            frozen.append(
                {
                    "frozen_prepass_sha": args.sha,
                    "historical_baseline_sha": BASELINE,
                    "volume": row["volume"],
                    "page": row["page"],
                    "line": row["line"],
                    "token_index": row["token_index"],
                    "tibetan_syllable": syllable,
                    "source_token": source,
                    "target": target,
                    "candidate_status":
                        "withheld_damage" if withheld else "positional",
                    "alignment_category": row["source_compatible_category"],
                    "damage_category": row["damage_scope"],
                    "historical_anchor_identity": anchor_identity,
                    "historical_anchor_provenance_class": anchor[
                        "historical_anchor_provenance_class"
                    ],
                    "family_identity_evidence": identity_evidence,
                    "row_local_review_result": (
                        "withheld_damage_or_marker"
                        if withheld
                        else "exact_tibetan_alignment_clean"
                    ),
                    "context_excerpt": row["context_excerpt"],
                }
            )
        for row in echoes:
            if (
                row["tibetan_syllable"] == syllable
                and row["additional_source_token"] == source
                and row["proposed_target"] == target
            ):
                frozen.append(
                    {
                        "frozen_prepass_sha": args.sha,
                        "historical_baseline_sha": BASELINE,
                        "volume": row["volume"],
                        "page": row["page"],
                        "line": row["line"],
                        "token_index": row["token_index"],
                        "tibetan_syllable": syllable,
                        "source_token": source,
                        "target": target,
                        "candidate_status": "echo",
                        "alignment_category": row["echo_category"],
                        "damage_category": (
                            row["echo_category"]
                            if row["echo_category"] in {
                                "uncertain", "marker_attached",
                                "damaged_reference",
                            }
                            else "none"
                        ),
                        "historical_anchor_identity": anchor_identity,
                        "historical_anchor_provenance_class": anchor[
                            "historical_anchor_provenance_class"
                        ],
                        "family_identity_evidence": identity_evidence,
                        "row_local_review_result": row["echo_category"],
                        "context_excerpt": row["context_excerpt"],
                    }
                )
    frozen.sort(key=lambda row: (
        list(families).index(row["tibetan_syllable"]),
        row["candidate_status"], row["volume"], int(row["page"]),
        int(row["line"]), int(row["token_index"]),
    ))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=FIELDS, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(frozen)
    print(
        f"wrote={len(frozen)} positional="
        f"{sum(row['candidate_status'] == 'positional' for row in frozen)} "
        f"withheld={sum(row['candidate_status'] == 'withheld_damage' for row in frozen)} "
        f"echo={sum(row['candidate_status'] == 'echo' for row in frozen)}"
    )


if __name__ == "__main__":
    main()
