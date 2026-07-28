#!/usr/bin/env python3
"""Audit final-ṅ targets against a checked-in pre-family campaign witness."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = "6322c7255cfba2fcfaf678cec656e65496ed5f12"
CONSENSUS_PATH = ROOT / "scripts/build_tibetan_final_ng_consensus.py"
SPEC = importlib.util.spec_from_file_location("final_ng_consensus", CONSENSUS_PATH)
assert SPEC and SPEC.loader
consensus = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = consensus
SPEC.loader.exec_module(consensus)

HISTORICAL_FIELDS = [
    "tibetan_syllable", "source_variant", "target",
    "historical_baseline_sha", "historical_anchor_present",
    "historical_volume", "historical_page", "historical_line",
    "historical_token_index", "historical_anchor_provenance_class",
    "historical_anchor_change_reason", "historical_anchor_change_evidence",
    "historical_context", "current_candidate_count",
    "current_damage_count", "current_marker_count",
]
REVIEWED_TARGET_FIELDS = [
    "tibetan_syllable", "source_variant", "target",
    "reviewed_same_tibetan_target_count", "reviewed_target_identities",
    "reviewed_target_reasons", "clean_candidate_count", "damaged_candidate_count",
    "marker_candidate_count", "conflicting_reviewed_targets",
    "eligibility", "sample_contexts",
]
CALIBRATION_FAMILIES = {
    "ཀྲོང": ("kron", "kroṅ"),
    "རྟིང": ("rtin", "rtiṅ"),
    "བགྲང": ("bgran", "bgraṅ"),
}


def git_show(ref: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return None
    return result.stdout


def read_tsv_text(text: str | None) -> list[dict[str, str]]:
    if not text:
        return []
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def read_current_rows(filename: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(
        (ROOT / "release/current/qa").glob(
            f"*/tibetan_cleanup_diagnostics/{filename}"
        )
    ):
        rows.extend(consensus.read_tsv(path))
    return rows


def collect_historical_aligned(ref: str) -> list[dict[str, str]]:
    aligned: list[dict[str, str]] = []
    for volume in ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"):
        path = f"release/current/qa/{volume}/{volume}_line_zones.tsv"
        for row in read_tsv_text(git_show(ref, path)):
            line = row["line_text"]
            syllables, tail, tail_start = consensus.tibetan_syllables_and_tail(line)
            if not syllables or not tail:
                continue
            latin = consensus.latin_headword_tokens(tail, len(syllables))
            if len(latin) < len(syllables):
                continue
            for syllable, (token, relative_start) in zip(syllables, latin):
                if not consensus.ends_in_tibetan_ng(syllable):
                    continue
                absolute_start = tail_start + relative_start
                token_index = next(
                    (
                        index
                        for index, match in enumerate(
                            consensus.POSTPROCESS_TOKEN_RE.finditer(line), start=1
                        )
                        if match.start() == absolute_start
                    ),
                    None,
                )
                if token_index is None:
                    continue
                aligned.append(
                    {
                        "volume": volume,
                        "page": row["page"],
                        "line": row["line"],
                        "token_index": str(token_index),
                        "tibetan_syllable": syllable,
                        "latin_token": token,
                        "context_excerpt": line,
                    }
                )
    return aligned


def historical_ledgers(ref: str) -> tuple[
    dict[tuple[str, ...], list[dict[str, str]]],
    dict[tuple[str, ...], list[dict[str, str]]],
    dict[tuple[str, ...], list[dict[str, str]]],
]:
    exact: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in read_tsv_text(
        git_show(ref, "data/reviewed_tibetan_exact_overrides.tsv")
    ):
        exact[
            (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["to_token"],
            )
        ].append(row)
    google: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    changes: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for volume in ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"):
        prefix = f"release/current/qa/{volume}/{volume}"
        for row in read_tsv_text(
            git_show(ref, f"{prefix}_alternate_witness_adoptions.tsv")
        ):
            google[
                (
                    volume, row.get("page", ""), row.get("line", ""),
                    row.get("token_index", ""), row.get("alternate_token", ""),
                )
            ].append(row)
        for row in read_tsv_text(git_show(ref, f"{prefix}_changes.tsv")):
            changes[
                (volume, row["page"], row["line"], row["to_token"])
            ].append(row)
    return exact, google, changes


def classify_historical_anchor(
    row: dict[str, str],
    exact: dict[tuple[str, ...], list[dict[str, str]]],
    google: dict[tuple[str, ...], list[dict[str, str]]],
    changes: dict[tuple[str, ...], list[dict[str, str]]],
) -> tuple[str, str, str]:
    key = (
        row["volume"], row["page"], row["line"], row["token_index"],
        row["latin_token"],
    )
    if exact.get(key):
        records = exact[key]
        return (
            "historical_pre_family_reviewed_exact",
            ";".join(sorted({item["reason"] for item in records})),
            ";".join(sorted({item["evidence"] for item in records})),
        )
    if google.get(key):
        return (
            "historical_pre_family_google_adopted",
            ";".join(sorted({
                item.get("reason", "") for item in google[key]
            })),
            "alternate_witness_adoption",
        )
    change_rows = changes.get(
        (row["volume"], row["page"], row["line"], row["latin_token"]), []
    )
    if change_rows:
        return (
            "historical_pre_family_other_postprocess",
            ";".join(sorted({item.get("reason", "") for item in change_rows})),
            ";".join(sorted({item.get("tier", "") for item in change_rows})),
        )
    return (
        "historical_pre_family_present_unattributed",
        "none",
        "checked_in_pre_family_campaign_witness",
    )


def build_historical_audit(ref: str) -> list[dict[str, str]]:
    candidates = read_current_rows(
        "tibetan_final_ng_source_compatible_candidates.tsv"
    )
    families: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        target = row["proposed_latin_target"]
        if target and row["source_compatible_category"] in {
            "source_compatible_single_anchor",
            "source_compatible_dominant_consensus",
            "source_compatible_damaged_context",
            "source_compatible_marker_attached",
        }:
            families[
                (
                    row["tibetan_syllable"],
                    row["source_latin_token"],
                    target,
                )
            ].append(row)
    for syllable, (source, target) in CALIBRATION_FAMILIES.items():
        families.setdefault((syllable, source, target), [])
    historical = collect_historical_aligned(ref)
    exact, google, changes = historical_ledgers(ref)
    audit: list[dict[str, str]] = []
    for (syllable, source, target), family in families.items():
        anchors = [
            row for row in historical
            if row["tibetan_syllable"] == syllable
            and row["latin_token"] == target
        ]
        if not anchors:
            audit.append(
                {
                    "tibetan_syllable": syllable,
                    "source_variant": source,
                    "target": target,
                    "historical_baseline_sha": ref,
                    "historical_anchor_present": "no",
                    "historical_volume": "",
                    "historical_page": "",
                    "historical_line": "",
                    "historical_token_index": "",
                    "historical_anchor_provenance_class":
                        "not_present_at_historical_baseline",
                    "historical_anchor_change_reason": "",
                    "historical_anchor_change_evidence": "",
                    "historical_context": "",
                    "current_candidate_count": str(len(family)),
                    "current_damage_count": str(sum(
                        row["source_compatible_category"]
                        == "source_compatible_damaged_context"
                        for row in family
                    )),
                    "current_marker_count": str(sum(
                        row["source_compatible_category"]
                        == "source_compatible_marker_attached"
                        for row in family
                    )),
                }
            )
            continue
        for anchor in anchors:
            classification, reason, evidence = classify_historical_anchor(
                anchor, exact, google, changes
            )
            audit.append(
                {
                    "tibetan_syllable": syllable,
                    "source_variant": source,
                    "target": target,
                    "historical_baseline_sha": ref,
                    "historical_anchor_present": "yes",
                    "historical_volume": anchor["volume"],
                    "historical_page": anchor["page"],
                    "historical_line": anchor["line"],
                    "historical_token_index": anchor["token_index"],
                    "historical_anchor_provenance_class": classification,
                    "historical_anchor_change_reason": reason,
                    "historical_anchor_change_evidence": evidence,
                    "historical_context": anchor["context_excerpt"],
                    "current_candidate_count": str(len(family)),
                    "current_damage_count": str(sum(
                        row["source_compatible_category"]
                        == "source_compatible_damaged_context"
                        for row in family
                    )),
                    "current_marker_count": str(sum(
                        row["source_compatible_category"]
                        == "source_compatible_marker_attached"
                        for row in family
                    )),
                }
            )
    return sorted(audit, key=lambda row: (
        row["tibetan_syllable"], row["source_variant"],
        row["historical_anchor_present"] != "yes",
        row["historical_volume"], int(row["historical_page"] or 0),
        int(row["historical_line"] or 0),
    ))


def build_reviewed_target_audit() -> list[dict[str, str]]:
    candidates = read_current_rows(
        "tibetan_final_ng_source_compatible_candidates.tsv"
    )
    aligned, _accepted = consensus.collect_aligned_rows(ROOT / "release/current")
    exact_rows = consensus.read_tsv(
        ROOT / "data/reviewed_tibetan_exact_overrides.tsv"
    )
    exact_by_key = {
        (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["to_token"],
        ): row
        for row in exact_rows
    }
    reviewed: dict[tuple[str, str], list[tuple[dict[str, str], dict[str, str]]]] = (
        defaultdict(list)
    )
    for row in aligned:
        key = (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["latin_token"],
        )
        override = exact_by_key.get(key)
        if override and consensus.is_genuine_dotted_final_ng_anchor(
            row["latin_token"], row["tibetan_syllable"]
        ):
            reviewed[(row["tibetan_syllable"], row["latin_token"])].append(
                (row, override)
            )
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        if row["source_latin_token"][-1:] in consensus.SOURCE_FINALS:
            grouped[
                (row["tibetan_syllable"], row["source_latin_token"])
            ].append(row)
    audit: list[dict[str, str]] = []
    for (syllable, source), family in grouped.items():
        targets = {
            target: records
            for (target_syllable, target), records in reviewed.items()
            if target_syllable == syllable
            and consensus.source_compatible_pair(source, target)
        }
        for target, records in targets.items():
            clean = [
                row for row in family
                if row["damage_scope"] == "none"
                and row["source_compatible_category"]
                not in {
                    "source_compatible_marker_attached",
                    "source_compatible_not_final_ng_only",
                }
                and row["alignment_review_status"]
                == "exact_source_signature_supported"
            ]
            competing = sorted(item for item in targets if item != target)
            audit.append(
                {
                    "tibetan_syllable": syllable,
                    "source_variant": source,
                    "target": target,
                    "reviewed_same_tibetan_target_count": str(len(records)),
                    "reviewed_target_identities": ";".join(
                        f"{row['volume']}:{row['page']}:{row['line']}:"
                        f"{row['token_index']}"
                        for row, _override in records
                    ),
                    "reviewed_target_reasons": ";".join(sorted({
                        override["reason"] for _row, override in records
                    })),
                    "clean_candidate_count": str(len(clean)),
                    "damaged_candidate_count": str(sum(
                        row["damage_scope"] != "none" for row in family
                    )),
                    "marker_candidate_count": str(sum(
                        row["source_compatible_category"]
                        == "source_compatible_marker_attached"
                        for row in family
                    )),
                    "conflicting_reviewed_targets": ";".join(competing),
                    "eligibility": (
                        "reviewed_same_tibetan_target_final_nasal_only"
                        if clean and not competing else "withhold"
                    ),
                    "sample_contexts": " || ".join(
                        row["context_excerpt"] for row in clean[:3]
                    ),
                }
            )
    return sorted(audit, key=lambda row: (
        row["eligibility"] !=
        "reviewed_same_tibetan_target_final_nasal_only",
        -int(row["clean_candidate_count"]),
        row["tibetan_syllable"], row["source_variant"],
    ))


def write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    consensus.write_tsv(path, rows, fields)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument(
        "--historical-output",
        type=Path,
        default=ROOT / "data/final_ng_historical_witness_audit.tsv",
    )
    parser.add_argument(
        "--reviewed-target-output",
        type=Path,
        default=ROOT / "data/final_ng_reviewed_target_propagation.tsv",
    )
    args = parser.parse_args()
    historical = build_historical_audit(args.baseline)
    reviewed = build_reviewed_target_audit()
    write(args.historical_output, historical, HISTORICAL_FIELDS)
    write(args.reviewed_target_output, reviewed, REVIEWED_TARGET_FIELDS)
    present_families = {
        (row["tibetan_syllable"], row["source_variant"], row["target"])
        for row in historical if row["historical_anchor_present"] == "yes"
    }
    eligible = sum(
        row["eligibility"]
        == "reviewed_same_tibetan_target_final_nasal_only"
        for row in reviewed
    )
    print(
        f"historical_rows={len(historical)} "
        f"historically_supported_families={len(present_families)} "
        f"reviewed_target_eligible_families={eligible}"
    )


if __name__ == "__main__":
    main()
