#!/usr/bin/env python3
"""Freeze the explicitly authorized, provenance-reviewed one-anchor pilot."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QA_ROOT = ROOT / "release/current/qa"
PILOT = {
    "ཀྲོང": ("kron", "kroṅ", "direct_repeated_tibetan_alignment"),
    "རྟིང": ("rtin", "rtiṅ", "explicit_same_entry_repetition"),
    "བགྲང": ("bgran", "bgraṅ", "explicit_same_entry_repetition"),
}
FIELDS = [
    "frozen_prepass_sha", "volume", "page", "line", "token_index",
    "tibetan_syllable", "source_token", "target", "candidate_status",
    "alignment_category", "damage_category", "anchor_provenance",
    "anchor_identity", "lemma_identity_evidence", "manual_review_rationale",
    "context_excerpt",
]


def read_rows(filename: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(QA_ROOT.glob(f"*/tibetan_cleanup_diagnostics/{filename}")):
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidates = read_rows("tibetan_final_ng_source_compatible_candidates.tsv")
    provenance = read_rows("tibetan_final_ng_dotted_anchor_provenance.tsv")
    echoes = read_rows("tibetan_final_ng_same_entry_echo_candidates.tsv")
    frozen: list[dict[str, str]] = []
    for syllable, (source, target, identity_cue) in PILOT.items():
        anchors = [
            row for row in provenance
            if row["tibetan_syllable"] == syllable
            and row["current_dotted_token"] == target
            and row["provenance_class"] == "base_ocr_dotted"
        ]
        if len(anchors) != 1:
            raise ValueError(
                f"{syllable}: expected one independent base anchor, got {len(anchors)}"
            )
        anchor = anchors[0]
        anchor_identity = (
            f"{anchor['volume']}:{anchor['page']}:{anchor['line']}:"
            f"{anchor['token_index']}:{target}"
        )
        family_candidates = [
            row for row in candidates
            if row["tibetan_syllable"] == syllable
            and row["source_latin_token"] == source
            and row["proposed_latin_target"] == target
            and row["source_compatible_category"]
            == "source_compatible_single_anchor"
            and row["damage_scope"] == "none"
        ]
        if not family_candidates:
            raise ValueError(f"{syllable}: no clean single-anchor candidates")
        for row in family_candidates:
            frozen.append(
                {
                    "frozen_prepass_sha": args.sha,
                    "volume": row["volume"],
                    "page": row["page"],
                    "line": row["line"],
                    "token_index": row["token_index"],
                    "tibetan_syllable": syllable,
                    "source_token": source,
                    "target": target,
                    "candidate_status": "positional",
                    "alignment_category": row["source_compatible_category"],
                    "damage_category": "none",
                    "anchor_provenance": "base_ocr_dotted",
                    "anchor_identity": anchor_identity,
                    "lemma_identity_evidence": identity_cue,
                    "manual_review_rationale": (
                        "Exact Tibetan identity and token position reviewed; "
                        "independent base anchor plus separate entry-identity cue."
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
                            if row["echo_category"]
                            in {"uncertain", "marker_attached", "damaged_reference"}
                            else "none"
                        ),
                        "anchor_provenance": "base_ocr_dotted",
                        "anchor_identity": anchor_identity,
                        "lemma_identity_evidence": row["echo_category"],
                        "manual_review_rationale": "Frozen for explicit A/D/R/RE review.",
                        "context_excerpt": row["context_excerpt"],
                    }
                )

    frozen.sort(
        key=lambda row: (
            row["tibetan_syllable"], row["candidate_status"], row["volume"],
            int(row["page"]), int(row["line"]), int(row["token_index"]),
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=FIELDS, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(frozen)
    counts = {
        status: sum(row["candidate_status"] == status for row in frozen)
        for status in ("positional", "echo")
    }
    print(f"wrote {len(frozen)} rows: {counts}")


if __name__ == "__main__":
    main()
