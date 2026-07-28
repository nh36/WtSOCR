#!/usr/bin/env python3
"""Build corpus-conditioned Tibetan/Latin transcription integrity diagnostics."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSENSUS_PATH = ROOT / "scripts/build_tibetan_final_ng_consensus.py"
SPEC = importlib.util.spec_from_file_location("final_ng_consensus", CONSENSUS_PATH)
assert SPEC and SPEC.loader
consensus = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = consensus
SPEC.loader.exec_module(consensus)

REGISTRY_PATH = ROOT / "data/tibetan_latin_feature_registry.tsv"
OVERRIDES_PATH = ROOT / "data/reviewed_tibetan_exact_overrides.tsv"
SUPERSESSIONS_PATH = ROOT / "data/reviewed_correction_supersessions.tsv"

DIAGNOSTIC_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "current_latin_token", "integrity_status", "integrity_pass",
    "expected_high_confidence_features", "observed_features",
    "violated_rules", "canonical_full_target", "canonical_target_evidence",
    "domain_context", "damage_scope", "marker_attached", "context_excerpt",
]
BACKAUDIT_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "original_source", "applied_target", "correction_reason",
    "correction_batch", "target_integrity_status",
    "violated_transcription_feature", "proposed_disposition",
    "context_excerpt",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def load_registry(path: Path = REGISTRY_PATH) -> list[dict[str, str]]:
    rows = read_tsv(path)
    required = {
        "tibetan_feature", "feature_type", "expected_latin_feature",
        "evidence_class", "confidence", "review_status",
    }
    if rows and not required.issubset(rows[0]):
        raise ValueError("Tibetan/Latin feature registry is missing required columns")
    return rows


def authoritative_rules(
    registry: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    return [
        row for row in (registry or load_registry())
        if row["review_status"] in {"reviewed", "high_confidence"}
        and row["confidence"] == "high"
    ]


def classify_domain(zone: str, line: str) -> str:
    if zone in {"latin_other", "german_prose_with_translit"}:
        return "bibliography_citation_or_prose"
    lowered = line.lower()
    if "skt." in lowered or "skr." in lowered:
        return "sanskrit_or_indic_transcription"
    if "npr." in lowered:
        return "tibetan_proper_name"
    if zone in {"headword_line", "tibetan_only"}:
        return "ordinary_tibetan_lexical_or_compound"
    return "unclear"


def token_integrity(
    tibetan_syllable: str,
    latin_token: str,
    registry: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    expected: list[str] = []
    observed: list[str] = []
    violated: list[str] = []
    nonfinal_mismatch = False
    final_mismatch = False
    for rule in authoritative_rules(registry):
        feature = rule["tibetan_feature"]
        if feature not in tibetan_syllable:
            continue
        latin_feature = rule["expected_latin_feature"]
        feature_type = rule["feature_type"]
        if feature_type == "suffix_coda":
            if not consensus.ends_in_tibetan_ng(tibetan_syllable):
                continue
            expected.append(f"{feature}:{latin_feature}")
            if latin_token.endswith(latin_feature):
                observed.append(latin_feature)
            else:
                final_mismatch = True
                violated.append(f"{feature_type}:{feature}->{latin_feature}")
            continue
        expected.append(f"{feature}:{latin_feature}")
        if latin_feature in latin_token:
            observed.append(latin_feature)
        else:
            nonfinal_mismatch = True
            violated.append(f"{feature_type}:{feature}->{latin_feature}")
    if nonfinal_mismatch and final_mismatch:
        status = "multiple_feature_mismatches"
    elif nonfinal_mismatch:
        status = "nonfinal_feature_mismatch"
    elif final_mismatch:
        status = "final_feature_mismatch_only"
    elif expected:
        status = "transcription_integrity_pass"
    else:
        status = "insufficient_feature_coverage"
    return {
        "integrity_status": status,
        "integrity_pass": "yes" if not nonfinal_mismatch else "no",
        "expected": ";".join(expected),
        "observed": ";".join(observed),
        "violated": ";".join(violated),
    }


def collect_all_aligned(release_root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for volume_dir in sorted((release_root / "qa").glob("wts_*")):
        volume = volume_dir.name
        zones = read_tsv(volume_dir / f"{volume}_line_zones.tsv")
        for zone_row in zones:
            line = zone_row.get("line_text", "")
            syllables, tail, tail_start = consensus.tibetan_syllables_and_tail(line)
            if not syllables or not tail:
                continue
            latin = consensus.latin_headword_tokens(tail, len(syllables))
            if len(latin) < len(syllables):
                continue
            phrase_start = tail_start + latin[0][1]
            last_token, last_start = latin[len(syllables) - 1]
            phrase_end = tail_start + last_start + len(last_token)
            for syllable, (token, relative_start) in zip(syllables, latin):
                absolute_start = tail_start + relative_start
                token_index = next(
                    (
                        index for index, match in enumerate(
                            consensus.POSTPROCESS_TOKEN_RE.finditer(line), start=1
                        ) if match.start() == absolute_start
                    ),
                    0,
                )
                damage = consensus.classify_damage_scope(
                    line, tail_start, phrase_start, phrase_end,
                )
                rows.append({
                    "volume": volume,
                    "page": zone_row["page"],
                    "line": zone_row["line"],
                    "token_index": str(token_index),
                    "tibetan_syllable": syllable,
                    "latin_token": token,
                    "zone": zone_row.get("zone", ""),
                    "damage_scope": damage,
                    "marker_attached": (
                        "yes" if consensus.token_has_attached_marker(
                            line, token_index
                        ) else "no"
                    ),
                    "context_excerpt": line.rstrip(),
                })
    return rows


def build_diagnostics(release_root: Path) -> list[dict[str, str]]:
    exact = read_tsv(OVERRIDES_PATH)
    canonical = {
        (
            row["volume"], row["page"], row["line"], row["token_index"],
        ): row for row in exact
    }
    output: list[dict[str, str]] = []
    for row in collect_all_aligned(release_root):
        result = token_integrity(row["tibetan_syllable"], row["latin_token"])
        if row["marker_attached"] == "yes" or row["damage_scope"] not in {
            "none", "later_gloss_or_commentary",
        }:
            status = "marker_or_damage"
        else:
            status = result["integrity_status"]
        override = canonical.get(
            (row["volume"], row["page"], row["line"], row["token_index"])
        )
        output.append({
            "volume": row["volume"], "page": row["page"],
            "line": row["line"], "token_index": row["token_index"],
            "tibetan_syllable": row["tibetan_syllable"],
            "current_latin_token": row["latin_token"],
            "integrity_status": status,
            "integrity_pass": result["integrity_pass"],
            "expected_high_confidence_features": result["expected"],
            "observed_features": result["observed"],
            "violated_rules": result["violated"],
            "canonical_full_target": override["to_token"] if override else "",
            "canonical_target_evidence": override["reason"] if override else "",
            "domain_context": classify_domain(
                row["zone"], row["context_excerpt"]
            ),
            "damage_scope": row["damage_scope"],
            "marker_attached": row["marker_attached"],
            "context_excerpt": row["context_excerpt"],
        })
    return output


def build_backaudit(
    diagnostics: list[dict[str, str]],
) -> list[dict[str, str]]:
    by_key = {
        (row["volume"], row["page"], row["line"], row["token_index"]): row
        for row in diagnostics
    }
    rows: list[dict[str, str]] = []
    for override in read_tsv(OVERRIDES_PATH):
        if "final_ng" not in override["reason"] and "final_nasal" not in override["reason"]:
            continue
        current = by_key.get((
            override["volume"], override["page"], override["line"],
            override["token_index"],
        ))
        if not current:
            continue
        check = token_integrity(
            current["tibetan_syllable"], override["to_token"]
        )
        disposition = (
            "pass" if check["integrity_pass"] == "yes"
            else "supersede_high_confidence_feature_mismatch"
        )
        rows.append({
            "volume": override["volume"], "page": override["page"],
            "line": override["line"], "token_index": override["token_index"],
            "tibetan_syllable": current["tibetan_syllable"],
            "original_source": override["from_token"],
            "applied_target": override["to_token"],
            "correction_reason": override["reason"],
            "correction_batch": override["evidence"],
            "target_integrity_status": check["integrity_status"],
            "violated_transcription_feature": check["violated"],
            "proposed_disposition": disposition,
            "context_excerpt": current["context_excerpt"],
        })
    return rows


def validate_supersessions() -> None:
    overrides = read_tsv(OVERRIDES_PATH)
    active = {
        (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["from_token"],
        ): row for row in overrides
    }
    for row in read_tsv(SUPERSESSIONS_PATH):
        if row["status"] != "active":
            continue
        key = (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["original_source"],
        )
        override = active.get(key)
        if not override or override["to_token"] != row["superseding_target"]:
            raise ValueError(
                f"Supersession {key} does not have one effective target "
                f"{row['superseding_target']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, default=ROOT / "release/current")
    parser.add_argument(
        "--out-root",
        type=Path,
        default=ROOT / "work/final_ng_seed_clean_20260719T210000Z",
    )
    args = parser.parse_args()
    diagnostics = build_diagnostics(args.release_root)
    for volume in ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"):
        write_tsv(
            args.out_root / f"tibetan_cleanup_diagnostics_{volume}"
            / "tibetan_latin_integrity_candidates.tsv",
            [row for row in diagnostics if row["volume"] == volume],
            DIAGNOSTIC_FIELDS,
        )
    backaudit = build_backaudit(diagnostics)
    write_tsv(
        ROOT / "data/final_ng_transcription_integrity_backaudit.tsv",
        backaudit, BACKAUDIT_FIELDS,
    )
    validate_supersessions()
    counts = Counter(row["integrity_status"] for row in diagnostics)
    print(f"aligned_rows={len(diagnostics)}")
    for status, count in sorted(counts.items()):
        print(f"{status}={count}")
    print(
        "final_ng_targets="
        f"{len(backaudit)} mismatches="
        f"{sum(row['proposed_disposition'] != 'pass' for row in backaudit)}"
    )


if __name__ == "__main__":
    main()
