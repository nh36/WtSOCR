#!/usr/bin/env python3
"""Build corpus-conditioned Tibetan/Latin transcription integrity diagnostics."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
import unicodedata
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
EXCEPTIONS_PATH = ROOT / "data/reviewed_tibetan_transcription_exceptions.tsv"
OVERRIDES_PATH = ROOT / "data/reviewed_tibetan_exact_overrides.tsv"
SUPERSESSIONS_PATH = ROOT / "data/reviewed_correction_supersessions.tsv"
CANONICAL_PATH = ROOT / "data/tibetan_latin_canonical_syllables.tsv"

DIAGNOSTIC_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "current_latin_token", "integrity_status", "integrity_pass",
    "known_feature_violation", "feature_coverage",
    "transcription_gateway_status", "transcription_exception_status",
    "transcription_exception_scope",
    "alignment_confidence",
    "token_start", "token_end", "preceding_character",
    "following_character", "token_boundary_status",
    "expected_high_confidence_features", "observed_features",
    "violated_rules", "canonical_full_target", "canonical_target_evidence",
    "domain_context", "damage_scope", "marker_attached", "context_excerpt",
]
BACKAUDIT_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "original_source", "applied_target", "correction_reason",
    "correction_batch", "target_integrity_status",
    "known_feature_violation", "feature_coverage",
    "transcription_gateway_status",
    "transcription_exception_status", "transcription_exception_scope",
    "blocked_reason",
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


def load_exceptions(path: Path = EXCEPTIONS_PATH) -> dict[tuple[str, str], dict[str, str]]:
    return {
        (row["tibetan_syllable"], row["source_token"]): row
        for row in read_tsv(path)
    }


def load_canonical_forms() -> dict[str, set[str]]:
    global _CANONICAL_FORMS
    if _CANONICAL_FORMS is not None:
        return _CANONICAL_FORMS
    forms: dict[str, set[str]] = {}
    for row in read_tsv(CANONICAL_PATH):
        if row.get("canonical_status") != "canonical":
            continue
        forms[row["tibetan_syllable"]] = {
            item for item in row.get("canonical_forms", "").split(";") if item
        }
    _CANONICAL_FORMS = forms
    return forms


_CANONICAL_FORMS: dict[str, set[str]] | None = None


def tibetan_roles(syllable: str) -> dict[str, str]:
    """Return only conservative, directly observable orthographic roles.

    This is deliberately not a transliterator.  It resolves suffix ང and the
    reviewed root ཞ cases needed by authoritative rules; everything else stays
    unresolved rather than being guessed.
    """
    roles = {
        "prefix": "",
        "superscript": "",
        "root_consonant": "",
        "subjoined_consonant": "",
        "vowel": "",
        "suffix_coda": "ང" if consensus.ends_in_tibetan_ng(syllable) else "",
        "post_suffix": "",
        "orthographic_role_status": "partial",
    }
    reviewed_roots = [
        feature for feature in ("ཞ", "ཉ", "ཤ") if feature in syllable
    ]
    if not reviewed_roots and syllable.startswith("ང"):
        reviewed_roots.append("ང")
    if len(reviewed_roots) == 1:
        roles["root_consonant"] = reviewed_roots[0]
    subjoined = [c for c in syllable if "\u0f90" <= c <= "\u0fbc"]
    if len(subjoined) == 1:
        roles["subjoined_consonant"] = subjoined[0]
    vowels = [c for c in syllable if c in "ིེོུ"]
    if len(vowels) <= 1:
        roles["vowel"] = vowels[0] if vowels else "a"
    if roles["root_consonant"] and len(subjoined) <= 1 and len(vowels) <= 1:
        roles["orthographic_role_status"] = "resolved_reviewed_features"
    else:
        roles["orthographic_role_status"] = "orthographic_role_unresolved"
    return roles


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
    *,
    use_canonical: bool = True,
) -> dict[str, str]:
    expected: list[str] = []
    observed: list[str] = []
    violated: list[str] = []
    nonfinal_mismatch = False
    final_mismatch = False
    roles = tibetan_roles(tibetan_syllable)
    for rule in authoritative_rules(registry):
        feature = rule["tibetan_feature"]
        latin_feature = rule["expected_latin_feature"]
        feature_type = rule["feature_type"]
        if feature_type == "suffix_coda":
            if roles["suffix_coda"] != feature:
                continue
            expected.append(f"{feature}:{latin_feature}")
            if latin_token.endswith(latin_feature):
                observed.append(latin_feature)
            else:
                final_mismatch = True
                violated.append(f"{feature_type}:{feature}->{latin_feature}")
            continue
        if feature_type == "root_consonant":
            if roles["root_consonant"] != feature:
                continue
        elif feature not in tibetan_syllable:
            continue
        expected.append(f"{feature}:{latin_feature}")
        if latin_feature in latin_token:
            observed.append(latin_feature)
        else:
            nonfinal_mismatch = True
            violated.append(f"{feature_type}:{feature}->{latin_feature}")
    exceptions = load_exceptions()
    exception = exceptions.get((tibetan_syllable, latin_token))
    if not exception and latin_token.endswith("ṅ"):
        for final in "nñńňh":
            candidate_exception = exceptions.get(
                (tibetan_syllable, latin_token[:-1] + final)
            )
            if candidate_exception and candidate_exception.get(
                "exception_scope", "family_block"
            ) in {"canonical_target_block", "family_block", "alignment_block"}:
                exception = candidate_exception
                break
    exception_status = exception["status"] if exception else ""
    exception_scope = exception.get("exception_scope", "") if exception else ""
    exception_blocks = exception_status in {
        "known_multi_error_source",
        "source_variant_requires_manual_review",
        "foreign_or_alternate_transcription",
        "obvious_gloss_or_alignment_noise",
        "marker_or_damage",
    }
    canonical_forms = (
        load_canonical_forms().get(tibetan_syllable, set())
        if use_canonical else set()
    )
    canonical_match = latin_token in canonical_forms
    canonical_mismatch = bool(canonical_forms) and not canonical_match
    if exception_blocks:
        status = "reviewed_transcription_exception"
    elif canonical_mismatch and not (nonfinal_mismatch or final_mismatch):
        status = "canonical_syllable_mismatch"
    elif nonfinal_mismatch and final_mismatch:
        status = "multiple_feature_mismatches"
    elif nonfinal_mismatch:
        status = "nonfinal_feature_mismatch"
    elif final_mismatch:
        status = "final_feature_mismatch_only"
    elif expected:
        status = "transcription_integrity_pass"
    else:
        status = "insufficient_feature_coverage"
    known_violation = (
        nonfinal_mismatch or final_mismatch or exception_blocks
        or canonical_mismatch
    )
    if exception_blocks or nonfinal_mismatch:
        gateway = "blocked"
    elif canonical_match:
        gateway = "pass"
    elif canonical_mismatch:
        gateway = "blocked"
    else:
        gateway = "unresolved"
    coverage = (
        "sufficient" if canonical_match else "partial" if expected else "none"
    )
    return {
        "integrity_status": status,
        "integrity_pass": "yes" if gateway == "pass" else "no",
        "known_feature_violation": "yes" if known_violation else "no",
        "feature_coverage": coverage,
        "transcription_gateway_status": gateway,
        "transcription_exception_status": exception_status,
        "transcription_exception_scope": exception_scope,
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
                absolute_end = absolute_start + len(token)
                preceding = line[absolute_start - 1:absolute_start]
                following = line[absolute_end:absolute_end + 1]
                following_category = (
                    unicodedata.category(following) if following else ""
                )
                preceding_category = (
                    unicodedata.category(preceding) if preceding else ""
                )
                if following_category.startswith("M"):
                    boundary = "combining_mark_boundary_issue"
                elif following and following in "'’":
                    boundary = "token_boundary_ambiguous"
                elif following and following_category.startswith("L"):
                    boundary = "adjacent_transliteration_glyph_uncaptured"
                elif preceding and preceding_category.startswith("M"):
                    boundary = "combining_mark_boundary_issue"
                else:
                    boundary = "token_boundary_secure"
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
                    "token_start": str(absolute_start),
                    "token_end": str(absolute_end),
                    "preceding_character": preceding,
                    "following_character": following,
                    "token_boundary_status": boundary,
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
        if row["marker_attached"] == "yes" or row["damage_scope"] not in {
            "none", "later_gloss_or_commentary",
        }:
            alignment_confidence = "marker_or_damage"
        elif override:
            alignment_confidence = "secure_reviewed_alignment"
        elif row["zone"] in {"headword_line", "tibetan_only"}:
            alignment_confidence = "secure_positional_alignment"
        elif row["zone"] in {"latin_other", "german_prose_with_translit"}:
            alignment_confidence = "gloss_or_prose_noise"
        else:
            alignment_confidence = "probable_alignment"
        output.append({
            "volume": row["volume"], "page": row["page"],
            "line": row["line"], "token_index": row["token_index"],
            "tibetan_syllable": row["tibetan_syllable"],
            "current_latin_token": row["latin_token"],
            "integrity_status": status,
            "integrity_pass": result["integrity_pass"],
            "known_feature_violation": result["known_feature_violation"],
            "feature_coverage": result["feature_coverage"],
            "transcription_gateway_status": (
                "blocked" if status == "marker_or_damage"
                else result["transcription_gateway_status"]
            ),
            "transcription_exception_status":
                result["transcription_exception_status"],
            "transcription_exception_scope":
                result["transcription_exception_scope"],
            "alignment_confidence": alignment_confidence,
            "token_start": row["token_start"],
            "token_end": row["token_end"],
            "preceding_character": row["preceding_character"],
            "following_character": row["following_character"],
            "token_boundary_status": row["token_boundary_status"],
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
        superseded = any(
            row["status"] == "active"
            and row["volume"] == override["volume"]
            and row["page"] == override["page"]
            and row["line"] == override["line"]
            and row["token_index"] == override["token_index"]
            and row["old_target"] == override["to_token"]
            for row in read_tsv(SUPERSESSIONS_PATH)
        )
        if superseded:
            disposition = "superseded"
        elif check["transcription_gateway_status"] == "pass":
            disposition = "validated"
        elif check["transcription_gateway_status"] == "blocked":
            disposition = "blocked"
        else:
            disposition = "no_known_violation_but_incomplete"
        rows.append({
            "volume": override["volume"], "page": override["page"],
            "line": override["line"], "token_index": override["token_index"],
            "tibetan_syllable": current["tibetan_syllable"],
            "original_source": override["from_token"],
            "applied_target": override["to_token"],
            "correction_reason": override["reason"],
            "correction_batch": override["evidence"],
            "target_integrity_status": check["integrity_status"],
            "known_feature_violation": check["known_feature_violation"],
            "feature_coverage": check["feature_coverage"],
            "transcription_gateway_status":
                check["transcription_gateway_status"],
            "transcription_exception_status":
                check["transcription_exception_status"],
            "transcription_exception_scope":
                check["transcription_exception_scope"],
            "blocked_reason": (
                "reviewed_exception"
                if check["transcription_exception_status"]
                else "canonical_mismatch"
                if check["integrity_status"] == "canonical_syllable_mismatch"
                else "genuine_feature_violation"
                if check["known_feature_violation"] == "yes"
                else ""
            ),
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
        f"{len(backaudit)} validated="
        f"{sum(row['proposed_disposition'] == 'validated' for row in backaudit)} "
        f"unresolved={sum(row['proposed_disposition'] == 'no_known_violation_but_incomplete' for row in backaudit)} "
        f"blocked={sum(row['proposed_disposition'] == 'blocked' for row in backaudit)} "
        f"superseded={sum(row['proposed_disposition'] == 'superseded' for row in backaudit)}"
    )


if __name__ == "__main__":
    main()
