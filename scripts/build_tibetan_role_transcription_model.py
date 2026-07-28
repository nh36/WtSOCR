#!/usr/bin/env python3
"""Build corpus-internal Tibetan-role transcription evidence.

This module parses Tibetan orthographic roles without consulting Latin text,
then mines role contrasts only from non-circular canonical evidence.  It is
deliberately not a Tibetan transliterator.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import hashlib
import io
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


integrity = load_module(
    "role_model_integrity", ROOT / "scripts/build_tibetan_latin_integrity.py"
)
canonical_builder = load_module(
    "role_model_canonical",
    ROOT / "scripts/build_tibetan_latin_syllable_concordance.py",
)

SOURCE_SCOPE_PATH = ROOT / "data/reviewed_correction_source_scopes.tsv"
SOURCE_SHADOW_PATH = ROOT / "data/tibetan_latin_reviewed_source_dispositions.tsv"
CANONICAL_PATH = ROOT / "data/tibetan_latin_canonical_syllables.tsv"
CONCORDANCE_PATH = ROOT / "data/tibetan_latin_syllable_concordance.tsv"
DECISIONS_PATH = ROOT / "data/reviewed_tibetan_feature_mapping_decisions.tsv"
FEATURE_COMPOSITION_AUDIT_BASELINE = (
    "e278992cc9317fca3bbe638c3420391a9b47d2cd"
)
_TEACHING_DIVERSITY_CACHE: dict[str, tuple[set[str], set[str]]] | None = None

PREFIXES = set("གདབམའ")
SUPERSCRIPTS = set("རལས")
SUBJOINED_MEDIALS = set("ཡརལཝ")
SUFFIXES = set("གངདནབམའརལས")
POST_SUFFIXES = {"ད", "ས"}
VOWELS = {"ི": "i", "ུ": "u", "ེ": "e", "ོ": "o"}
ROLE_ORDER = (
    "prefix", "superscript", "root_consonant", "subjoined_consonants",
    "vowel", "suffix_coda", "post_suffix",
)
SUPPORTED_VOWEL_SIGNS = set(VOWELS)
SANSKRIT_EXTENSION_BASES = {
    chr(code) for code in range(0x0F6A, 0x0F6D)
}
SANSKRIT_EXTENSION_SUBJOINED = {
    chr(code) for code in range(0x0FBA, 0x0FBD)
}

PARSE_FIELDS = [
    "tibetan_syllable", "prefix", "superscript", "root_consonant",
    "subjoined_consonants", "vowel", "suffix_coda", "post_suffix",
    "orthographic_stack", "ambiguous_root_candidates",
    "role_parse_status", "role_parse_confidence", "rationale",
]
FEATURE_EVIDENCE_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "latin_source", "latin_target", "tibetan_role", "tibetan_feature",
    "latin_realization", "structural_unit", "evidence_provenance",
    "source_or_target", "independence_class", "feature_teaching_status",
    "domain", "alignment", "confidence",
]
MAPPING_FIELDS = [
    "rule_id", "tibetan_role", "tibetan_feature", "structural_context",
    "contrastive_delta", "evidence_kind", "full_role_realization_candidate",
    "proposed_latin_realization", "strong_canonical_syllables",
    "independent_feature_evidence_identities", "reviewed_explicit_support",
    "unaffected_reviewed_source_support", "minimal_pair_support",
    "alternate_witness_support", "supporting_volumes",
    "supporting_entry_clusters", "counterexamples",
    "competing_realizations", "domain_breakdown", "confidence",
    "recommendation",
]
BACKTEST_FIELDS = [
    "tibetan_syllable", "hidden_canonical_target", "canonical_tier",
    "role_parse_status", "prediction", "component_rule_ids",
    "leave_one_out_status", "reconstruction_status", "missing_roles",
]
COMPOSITION_FIELDS = [
    "tibetan_syllable", "observed_forms", "current_canonical_tier",
    "role_parse_status", "composition_status", "feature_composed_target",
    "component_rule_ids", "supporting_evidence_ids",
    "leave_one_out_status", "domain_compatibility", "correction_authority",
    "blocker",
]
DOMAIN_FIELDS = [
    "rule_id", "ordinary_lexical_support", "proper_name_support",
    "sanskrit_foreign_support", "unclear_support", "conflicts",
    "proper_name_compatible", "rationale",
]
GRAPH_FIELDS = [
    "from_node", "from_node_type", "edge_type", "to_node",
    "to_node_type", "evidence_identity", "dependency_edge",
    "teaching_allowed",
]
SIGN_FIELDS = [
    "code_point", "unicode_name", "sign_class", "syllable_count",
    "occurrence_count", "domains", "sample_syllables", "parser_treatment",
    "composition_safe",
]
ORTHOGRAPHY_AUDIT_FIELDS = [
    "tibetan_syllable", "feature_composed_target", "tibetan_signs",
    "parser_interpretation", "component_rule_ids", "domain",
    "unsupported_sign_status", "target_support_channel",
    "retain_or_downgrade", "rationale",
]
REVALIDATION_FIELDS = [
    "rule_id", "authority_basis", "historical_decision",
    "original_supporting_syllables", "current_qualifying_syllables",
    "current_qualifying_contrasts", "current_volumes",
    "current_entry_clusters", "conflicts", "evidence_kind",
    "strict_leave_one_out_minimum_support", "dependency_status",
    "effective_authority", "rationale",
]
DEPENDENCY_FIELDS = [
    "tibetan_syllable", "target", "component_rule_ids",
    "rule_evidence_syllables", "target_in_rule_evidence",
    "strict_leave_one_out_status", "structural_unit_dependencies",
    "domain_rule_dependencies", "target_support_channel",
    "authority_status",
]
MIGRATION_FIELDS = [
    "tibetan_syllable", "baseline_target", "current_target",
    "baseline_status", "current_status", "migration_disposition",
    "rationale",
]
CONFLICT_FIELDS = [
    "tibetan_syllable", "true_canonical", "predicted_form",
    "component_rule_ids", "parsed_roles", "predicted_role_spans",
    "canonical_segmentation", "first_divergence", "contributing_rules",
    "likely_missing_interaction", "rule_supporting_syllables",
    "disposition",
]
ROLE_SPAN_FIELDS = [
    "tibetan_syllable", "target", "target_authority",
    "tibetan_role", "tibetan_feature", "target_start", "target_end",
    "target_span", "rule_id", "structural_context", "domain_authority",
]
CORRECTION_AUTHORITY_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "observed_source", "target", "correction_reason", "evidence_label",
    "correction_batch", "correction_commit", "target_authority_at_decision",
    "canonical_target", "component_feature_rule_ids",
    "structural_unit_rule_ids", "strict_leave_one_out_result",
    "target_support_channel", "ocr_signature_ids",
    "edit_structural_locations", "gate0_alignment_status",
    "token_boundary_status", "domain_gate", "prior_exact_decision_status",
    "authority_snapshot_sha", "current_backaudit_status",
]
EXPANSION_FIELDS = [
    "tibetan_role", "tibetan_feature", "structural_context",
    "strong_canonical_missing_count", "single_unknown_count",
    "isolated_residual_realizations", "supporting_syllables",
    "supporting_volumes", "supporting_entry_clusters",
    "provisional_syllables_unlocked", "secure_outliers_unlocked",
    "final_ng_rows_unlocked", "induction_status", "blocker",
]
STRUCTURAL_FIELDS = [
    "structural_unit", "tibetan_context", "latin_realization",
    "supporting_syllables", "supporting_volumes", "counterexamples",
    "evidence_kind", "recommendation",
]
RECENT_CORRECTION_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "source", "target", "target_authority_at_correction",
    "component_feature_rules", "self_contribution",
    "strict_leave_one_out_status", "ocr_signatures", "domain_authority",
    "prior_exact_decision", "present_source_status",
    "present_target_status", "backaudit_disposition",
]
SOURCE_RECOVERY_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "observed_source", "reviewed_target", "source_disposition",
    "corrected_roles", "recovery_status", "recovered_roles",
    "structural_unit", "mapping_dependencies", "blocker",
]
CONVERGENCE_FIELDS = [
    "iteration", "effective_rule_count", "new_rule_ids",
    "new_residual_candidate_ids", "authority_changed", "converged",
]


def read(path: Path) -> list[dict[str, str]]:
    return integrity.read_tsv(path)


def write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    integrity.write_tsv(
        path,
        [{field: row.get(field, "") for field in fields} for row in rows],
        fields,
    )


def read_git_tsv(commit: str, relative_path: str) -> list[dict[str, str]]:
    content = subprocess.check_output(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=ROOT, text=True,
    )
    return list(csv.DictReader(io.StringIO(content), delimiter="\t"))


def base_consonant(char: str) -> str:
    code = ord(char)
    if 0x0F90 <= code <= 0x0FBC:
        candidate = chr(code - 0x50)
        return candidate if "\u0f40" <= candidate <= "\u0f6c" else ""
    return char if "\u0f40" <= char <= "\u0f6c" else ""


def classify_tibetan_sign(char: str) -> tuple[str, str, bool]:
    code = ord(char)
    name = unicodedata.name(char, "UNKNOWN")
    if char in "་།༔ ":
        return "punctuation_or_delimiter", "ignored_delimiter", True
    if char in SANSKRIT_EXTENSION_BASES or char in SANSKRIT_EXTENSION_SUBJOINED:
        return "sanskrit_extension_sign", "unsupported_indic_structure", False
    if "\u0f40" <= char <= "\u0f6c":
        return "base_consonant", "parsed_consonant", True
    if 0x0F90 <= code <= 0x0FBC:
        return "subjoined_consonant", "parsed_subjoined_consonant", True
    if char in SUPPORTED_VOWEL_SIGNS:
        return "supported_vowel", "parsed_vowel", True
    if char == "\u0f71":
        return "length_sign", "unsupported_vowel_length", False
    if char in {"\u0f7e", "\u0f7f"}:
        return "anusvara_or_visarga_like_sign", "unsupported_indic_coda", False
    if "VOWEL SIGN" in name:
        return "unsupported_vowel_sign", "unsupported_vowel", False
    if unicodedata.category(char).startswith("M"):
        return "other_combining_sign", "unsupported_combining_sign", False
    if "\u0f00" <= char <= "\u0fff":
        return "unknown_tibetan_sign", "unsupported_tibetan_sign", False
    return "non_tibetan", "outside_parser_scope", False


def unsupported_orthographic_signs(syllable: str) -> list[str]:
    return [
        char for char in unicodedata.normalize("NFC", syllable)
        if not classify_tibetan_sign(char)[2]
    ]


def _suffix_split(bases: list[str], onset_end: int) -> tuple[list[str], str, str]:
    trailing = bases[onset_end:]
    if not trailing:
        return [], "", ""
    if (
        len(trailing) >= 2 and trailing[-1] in POST_SUFFIXES
        and trailing[-2] in SUFFIXES
    ):
        return trailing[:-2], trailing[-2], trailing[-1]
    if trailing[-1] in SUFFIXES:
        return trailing[:-1], trailing[-1], ""
    return trailing, "", ""


def parse_tibetan_syllable(syllable: str) -> dict[str, str]:
    """Conservatively recover orthographic roles from Tibetan Unicode alone."""
    chars = [
        c for c in unicodedata.normalize("NFC", syllable)
        if c not in "་།༔ " and not unicodedata.category(c).startswith("M")
    ]
    # Tibetan vowel/subjoined signs are combining marks, so collect them from
    # the unfiltered input before interpreting consonant structure.
    original = list(unicodedata.normalize("NFC", syllable))
    vowel_signs = [c for c in original if c in VOWELS]
    subjoined_positions = [
        (index, base_consonant(c)) for index, c in enumerate(original)
        if 0x0F90 <= ord(c) <= 0x0FBC and base_consonant(c)
    ]
    base_positions = [
        (index, c) for index, c in enumerate(original)
        if "\u0f40" <= c <= "\u0f6c"
    ]
    result = {
        "tibetan_syllable": syllable, "prefix": "", "superscript": "",
        "root_consonant": "", "subjoined_consonants": "",
        "vowel": (
            VOWELS[vowel_signs[0]] if len(vowel_signs) == 1
            else "a" if not vowel_signs else ""
        ),
        "suffix_coda": "", "post_suffix": "", "orthographic_stack": "",
        "ambiguous_root_candidates": "", "role_parse_status": "unparsed",
        "role_parse_confidence": "none", "rationale": "",
    }
    unsupported = unsupported_orthographic_signs(syllable)
    if len(vowel_signs) > 1:
        result["role_parse_status"] = "unsupported_orthographic_sign"
        result["role_parse_confidence"] = "none"
        result["rationale"] = "Multiple Tibetan vowel signs are not modelled."
        return result
    if unsupported:
        result["role_parse_status"] = "unsupported_orthographic_sign"
        result["role_parse_confidence"] = "none"
        result["rationale"] = "Unsupported transcription-bearing Tibetan signs: " + ",".join(
            f"U+{ord(char):04X}" for char in unsupported
        )
        return result
    if not base_positions:
        result["rationale"] = "No base consonant."
        return result

    bases = [c for _, c in base_positions]
    if subjoined_positions:
        first_sub_index, first_sub = subjoined_positions[0]
        preceding = [item for item in base_positions if item[0] < first_sub_index]
        following = [item for item in base_positions if item[0] > first_sub_index]
        if not preceding:
            result["rationale"] = "Subjoined stack lacks a visible base."
            return result
        stack_base = preceding[-1][1]
        if stack_base in SUPERSCRIPTS and first_sub not in SUBJOINED_MEDIALS:
            root = first_sub
            superscript = stack_base
            subjoined = "".join(c for _, c in subjoined_positions[1:])
            onset_bases = preceding[:-1]
        else:
            root = stack_base
            superscript = ""
            subjoined = "".join(c for _, c in subjoined_positions)
            onset_bases = preceding[:-1]
        prefix = onset_bases[-1][1] if len(onset_bases) == 1 \
            and onset_bases[-1][1] in PREFIXES else ""
        unresolved_onset = onset_bases[:-1] if prefix else onset_bases
        trailing_bases = [c for _, c in following]
        leftovers, suffix, post = _suffix_split(trailing_bases, 0)
        result.update({
            "prefix": prefix, "superscript": superscript,
            "root_consonant": root, "subjoined_consonants": subjoined,
            "suffix_coda": suffix, "post_suffix": post,
            "orthographic_stack": superscript + root + subjoined,
        })
        if unresolved_onset or leftovers:
            result["role_parse_status"] = "partially_resolved"
            result["role_parse_confidence"] = "medium"
            result["ambiguous_root_candidates"] = ";".join(
                dict.fromkeys(
                    [c for _, c in unresolved_onset] + leftovers
                )
            )
            result["rationale"] = "Stack resolved; extra consonants remain ambiguous."
        else:
            result["role_parse_status"] = "fully_resolved"
            result["role_parse_confidence"] = "high"
            result["rationale"] = "Unicode stack and trailing suffix roles resolve uniquely."
        return result

    candidates: list[dict[str, str]] = []
    for root_index, root in enumerate(bases):
        before, after = bases[:root_index], bases[root_index + 1:]
        if len(before) > 1 or (before and before[0] not in PREFIXES):
            continue
        leftovers, suffix, post = _suffix_split(after, 0)
        if leftovers:
            continue
        candidates.append({
            "prefix": before[0] if before else "", "root_consonant": root,
            "suffix_coda": suffix, "post_suffix": post,
        })
    # Prefer a prefix interpretation when it is the only candidate supported
    # by a recognized prefix and a valid suffix sequence.
    unique = {
        (c["prefix"], c["root_consonant"], c["suffix_coda"], c["post_suffix"]):
        c for c in candidates
    }
    candidates = list(unique.values())
    if len(candidates) == 1:
        chosen = candidates[0]
        result.update(chosen)
        result["orthographic_stack"] = chosen["root_consonant"]
        result["role_parse_status"] = "fully_resolved"
        result["role_parse_confidence"] = "high"
        result["rationale"] = "One prefix/root/suffix parse is structurally possible."
    elif candidates:
        result["ambiguous_root_candidates"] = ";".join(
            dict.fromkeys(c["root_consonant"] for c in candidates)
        )
        result["role_parse_status"] = "ambiguous_root"
        result["role_parse_confidence"] = "low"
        result["rationale"] = "Multiple Tibetan-only root parses remain possible."
    else:
        result["role_parse_status"] = "unusual_stack"
        result["role_parse_confidence"] = "none"
        result["rationale"] = "Consonant sequence does not match conservative role patterns."
    return result


def identity(row: dict[str, str]) -> str:
    return ":".join(
        row.get(field, "") for field in ("volume", "page", "line", "token_index")
    )


def changed_spans(source: str, target: str) -> list[dict[str, str]]:
    return canonical_builder.edit_operations(source, target)


def feature_teaching_evidence(
    parses: dict[str, dict[str, str]],
    rules: dict[tuple[str, str], dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    aligned = integrity.collect_all_aligned(ROOT / "release/current")
    diag = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in integrity.build_diagnostics(ROOT / "release/current")
    }
    aligned_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in aligned
    }
    source_scopes = {r["reason"]: r for r in read(SOURCE_SCOPE_PATH)}
    evidence: list[dict[str, str]] = []
    for override in read(integrity.OVERRIDES_PATH):
        key = tuple(override[f] for f in ("volume", "page", "line", "token_index"))
        row = aligned_by_key.get(key)
        check = diag.get(key, {})
        if not row:
            continue
        parse = parses.get(row["tibetan_syllable"], {})
        scope = source_scopes[override["reason"]]
        operations = changed_spans(override["from_token"], override["to_token"])
        common = {
            "volume": override["volume"], "page": override["page"],
            "line": override["line"], "token_index": override["token_index"],
            "tibetan_syllable": row["tibetan_syllable"],
            "latin_source": override["from_token"],
            "latin_target": override["to_token"],
            "evidence_provenance": override["reason"],
            "domain": check.get("domain_context", ""),
            "alignment": check.get("alignment_confidence", ""),
        }
        if scope["source_disposition"] in {
            "full_source_noncanonical", "superseded_wrong_target",
            "unknown_source_disposition",
        }:
            evidence.append({
                **common, "tibetan_role": "", "tibetan_feature": "",
                "latin_realization": "", "structural_unit": "full_token",
                "source_or_target": "source", "independence_class": "reviewed",
                "feature_teaching_status": "not_feature_evidence",
                "confidence": "high",
            })
            continue
        if scope["corrected_tibetan_roles"] == "suffix_coda" \
                and override["to_token"].endswith("ṅ"):
            if parse.get("suffix_coda") != "ང":
                evidence.append({
                    **common, "tibetan_role": "suffix_coda",
                    "tibetan_feature": "", "latin_realization": "",
                    "structural_unit": "token_final",
                    "source_or_target": "target",
                    "independence_class": "reviewed",
                    "feature_teaching_status": "role_unresolved",
                    "confidence": "none",
                })
                continue
            evidence.append({
                **common, "tibetan_role": "suffix_coda",
                "tibetan_feature": parse.get("suffix_coda", ""),
                "latin_realization": "ṅ", "structural_unit": "token_final",
                "source_or_target": "target", "independence_class": "reviewed",
                "feature_teaching_status": "reviewed_explicit_feature_evidence",
                "confidence": "high",
            })
            if scope["unaffected_source_may_teach"] == "yes":
                evidence.append({
                    **common, "tibetan_role": "pre_coda_structural_unit",
                    "tibetan_feature": row["tibetan_syllable"][:-1],
                    "latin_realization": override["from_token"][:-1],
                    "structural_unit": "pre_coda_stem",
                    "source_or_target": "source",
                    "independence_class": "historical_source",
                    "feature_teaching_status":
                        "unaffected_feature_from_reviewed_source",
                    "confidence": "medium",
                })
            continue
        if scope["corrected_tibetan_roles"] == "root_consonant" \
                and parse.get("root_consonant") == "ཞ" \
                and "ź" in override["to_token"]:
            evidence.append({
                **common, "tibetan_role": "root_consonant",
                "tibetan_feature": "ཞ", "latin_realization": "ź",
                "structural_unit": "root", "source_or_target": "target",
                "independence_class": "reviewed",
                "feature_teaching_status": "reviewed_explicit_feature_evidence",
                "confidence": "high",
            })
        if scope["unaffected_source_may_teach"] == "yes" and operations:
            unchanged = override["from_token"]
            for op in sorted(
                operations, key=lambda item: int(item["source_position"]),
                reverse=True,
            ):
                start = int(op["source_position"])
                unchanged = unchanged[:start] + "□" + unchanged[
                    start + len(op["source_span"]):
                ]
            evidence.append({
                **common, "tibetan_role": "unsegmented_structural_unit",
                "tibetan_feature": row["tibetan_syllable"],
                "latin_realization": unchanged,
                "structural_unit": "unaffected_span_support",
                "source_or_target": "source",
                "independence_class": "historical_source",
                "feature_teaching_status":
                    "unaffected_feature_from_reviewed_source",
                "confidence": "medium",
            })
        if (
            rules
            and scope["unaffected_source_may_teach"] == "yes"
            and parse.get("role_parse_status") == "fully_resolved"
        ):
            changed_source_positions = set()
            for operation in operations:
                start = int(operation["source_position"])
                changed_source_positions.update(
                    range(start, start + len(operation["source_span"]))
                )
            cursor = 0
            recovered: list[tuple[str, str, str, int, int]] = []
            usable = True
            corrected_roles = {
                item for item in scope["corrected_tibetan_roles"].split(";")
                if item
            }
            for role in ROLE_ORDER:
                feature = parse.get(role, "")
                if not feature:
                    continue
                if role in corrected_roles:
                    matching_operations = [
                        operation for operation in operations
                        if int(operation["source_position"]) == cursor
                    ]
                    if len(matching_operations) != 1:
                        usable = False
                        break
                    operation = matching_operations[0]
                    cursor += len(operation["source_span"])
                    continue
                rule = rules.get((role, feature))
                if not rule or not strict_rule_available(
                    rule, row["tibetan_syllable"]
                ):
                    usable = False
                    break
                realization = rule["latin_realization"]
                start, end = cursor, cursor + len(realization)
                if override["from_token"][start:end] != realization:
                    usable = False
                    break
                recovered.append((role, feature, realization, start, end))
                cursor = end
            if usable and cursor == len(override["from_token"]):
                for role, feature, realization, start, end in recovered:
                    if changed_source_positions.intersection(range(start, end)):
                        continue
                    evidence.append({
                        **common, "tibetan_role": role,
                        "tibetan_feature": feature,
                        "latin_realization": realization,
                        "structural_unit": f"resolved_{role}_span",
                        "evidence_provenance": (
                            override["reason"] + "|segmented_by:"
                            + rules[(role, feature)]["rule_id"]
                        ),
                        "source_or_target": "source",
                        "independence_class": "historical_source",
                        "feature_teaching_status":
                            "unaffected_role_evidence_from_reviewed_source",
                        "confidence": "high",
                    })
    return evidence


def canonical_forms() -> list[dict[str, str]]:
    return [
        row for row in read(CANONICAL_PATH)
        if row["canonical_confidence_tier"] in {
            "canonical_reviewed", "canonical_independent_strong"
        } and row["canonical_forms"] and ";" not in row["canonical_forms"]
    ]


def classify_contrast_evidence(
    role: str,
    left_feature: str,
    right_feature: str,
    operation: dict[str, str],
) -> str:
    left_real = operation["source_span"]
    right_real = operation["target_span"]
    if (
        operation["operation_type"] == "punctuation_confusion"
        or role in {"prefix", "superscript", "subjoined_consonants"}
        and ("." in left_real or "." in right_real)
    ):
        return "multi_role_interaction"
    if left_feature and right_feature and left_real and right_real:
        return "full_realization_isolated"
    if bool(left_feature) != bool(right_feature) and (
        not left_real or not right_real
    ):
        return "zero_realization_isolated"
    if left_feature and right_feature and (
        not left_real or not right_real
    ):
        return "contrastive_delta_only"
    return "alignment_ambiguous"


def contrastive_candidates(
    canonical: list[dict[str, str]],
    parses: dict[str, dict[str, str]],
    feature_evidence: list[dict[str, str]],
) -> list[dict[str, str]]:
    items = [
        (row, parses[row["tibetan_syllable"]])
        for row in canonical
        if parses[row["tibetan_syllable"]]["role_parse_status"]
        == "fully_resolved"
    ]
    support: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    pairs: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    volumes: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    clusters: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    evidence_kinds: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    deltas: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    competing: dict[tuple[str, str], set[str]] = defaultdict(set)
    teaching_clusters: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in read(
        ROOT / "data/tibetan_latin_canonical_teaching_evidence.tsv"
    ):
        if item["canonical_teaching_status"] != "independent_teaching_evidence":
            continue
        teaching_clusters[
            (item["tibetan_syllable"], item["latin_form"])
        ].add(f"{item['volume']}:{item['page']}")
    for index, (left, lp) in enumerate(items):
        left_roles = tuple(lp[r] for r in ROLE_ORDER)
        for right, rp in items[index + 1:]:
            right_roles = tuple(rp[r] for r in ROLE_ORDER)
            differing = [
                role for role, a, b in zip(ROLE_ORDER, left_roles, right_roles)
                if a != b
            ]
            if len(differing) != 1:
                continue
            operations = canonical_builder.edit_operations(
                left["canonical_forms"], right["canonical_forms"]
            )
            if len(operations) != 1:
                continue
            op = operations[0]
            role = differing[0]
            left_real, right_real = op["source_span"], op["target_span"]
            left_feature, right_feature = lp[role], rp[role]
            pair_kind = classify_contrast_evidence(
                role, left_feature, right_feature, op
            )
            for row, parse, realization in (
                (left, lp, left_real), (right, rp, right_real)
            ):
                feature = parse[role]
                key = (role, feature, realization)
                deltas[key].add(
                    f"{op['source_span']}→{op['target_span']}"
                )
                evidence_kinds[key].add(pair_kind)
                if pair_kind not in {
                    "full_realization_isolated", "zero_realization_isolated"
                }:
                    continue
                support[key].add(row["tibetan_syllable"])
                pairs[key].add(
                    f"{left['tibetan_syllable']}:{left['canonical_forms']}↔"
                    f"{right['tibetan_syllable']}:{right['canonical_forms']}"
                )
                volumes[key].update(
                    v for v in row["supporting_volumes"].split(";") if v
                )
                clusters[key].update(teaching_clusters.get(
                    (row["tibetan_syllable"], row["canonical_forms"]), set()
                ))
                competing[(role, feature)].add(realization)

    explicit = {
        (r["tibetan_role"], r["tibetan_feature"], r["latin_realization"])
        for r in feature_evidence
        if r["feature_teaching_status"] == "reviewed_explicit_feature_evidence"
    }
    decisions = {
        (r["tibetan_role"], r["tibetan_feature"], r["latin_realization"]): r
        for r in read(DECISIONS_PATH) if r["decision"] == "A"
    }
    keys = set(support) | set(deltas) | explicit | set(decisions)
    rows: list[dict[str, str]] = []
    def automatic_rule_id(key: tuple[str, str, str]) -> str:
        digest = hashlib.sha1(
            "\u241f".join(key).encode("utf-8")
        ).hexdigest()[:12].upper()
        return f"CORPUS_{digest}"

    for role, feature, realization in sorted(keys):
        key = (role, feature, realization)
        alternatives = competing.get((role, feature), set()) - {realization}
        reviewed_count = sum(
            r["tibetan_role"] == role and r["tibetan_feature"] == feature
            and r["latin_realization"] == realization
            and r["feature_teaching_status"]
            == "reviewed_explicit_feature_evidence"
            for r in feature_evidence
        )
        if key in decisions:
            confidence, recommendation = "reviewed", "feature_reviewed"
            rule_id = decisions[key]["rule_id"]
        elif len(support[key]) >= 3 and len(pairs[key]) >= 2 and not alternatives:
            confidence, recommendation = (
                "high", "feature_independent_strong_candidate",
            )
            rule_id = automatic_rule_id(key)
        elif support[key]:
            confidence, recommendation = "provisional", "feature_provisional"
            rule_id = automatic_rule_id(key)
        else:
            confidence, recommendation = "reviewed", "feature_reviewed"
            rule_id = decisions.get(key, {}).get("rule_id", "REVIEWED")
        rows.append({
            "rule_id": rule_id, "tibetan_role": role,
            "tibetan_feature": feature, "structural_context": "contrastive",
            "contrastive_delta": ";".join(sorted(deltas[key])),
            "evidence_kind": ";".join(sorted(evidence_kinds[key]))
                or "reviewed_explicit_feature",
            "full_role_realization_candidate": (
                realization if any(kind in {
                    "full_realization_isolated", "zero_realization_isolated"
                } for kind in evidence_kinds[key])
                or key in decisions else ""
            ),
            "proposed_latin_realization": realization,
            "strong_canonical_syllables": ";".join(sorted(support[key])),
            "independent_feature_evidence_identities": "",
            "reviewed_explicit_support": str(reviewed_count),
            "unaffected_reviewed_source_support": str(sum(
                r["tibetan_role"] == role and r["tibetan_feature"] == feature
                and r["latin_realization"] == realization
                and r["feature_teaching_status"]
                == "unaffected_feature_from_reviewed_source"
                for r in feature_evidence
            )),
            "minimal_pair_support": " || ".join(sorted(pairs[key])),
            "alternate_witness_support": "0",
            "supporting_volumes": ";".join(sorted(volumes[key])),
            "supporting_entry_clusters": ";".join(sorted(clusters[key])),
            "counterexamples": "",
            "competing_realizations": ";".join(sorted(alternatives)),
            "domain_breakdown": "ordinary_tibetan_lexical_or_compound",
            "confidence": confidence, "recommendation": recommendation,
        })
    return rows


def authoritative_rules(
    candidates: list[dict[str, str]],
) -> dict[tuple[str, str], dict[str, str]]:
    decisions = {
        row["rule_id"]: row for row in read(DECISIONS_PATH)
        if row["decision"] == "A"
    }
    result = {}
    for row in candidates:
        decision = decisions.get(row["rule_id"])
        if not decision:
            continue
        basis = (
            "empirical_corpus"
            if decision.get("provenance", "").startswith("corpus_internal_")
            else "explicit_review"
        )
        if basis == "empirical_corpus" and not empirical_rule_qualifies(row):
            continue
        result[(row["tibetan_role"], row["tibetan_feature"])] = {
            **row, **decision, "authority_basis": basis,
        }
    return result


def _pair_items(rule: dict[str, str]) -> list[str]:
    return [
        item for item in rule.get("minimal_pair_support", "").split(" || ")
        if item
    ]


def _supporting_syllables(
    rule: dict[str, str], excluded_syllable: str = "",
) -> set[str]:
    return {
        item for item in rule.get("strong_canonical_syllables", "").split(";")
        if item and item != excluded_syllable
    }


def _support_diversity(
    syllables: set[str],
) -> tuple[set[str], set[str]]:
    global _TEACHING_DIVERSITY_CACHE
    if _TEACHING_DIVERSITY_CACHE is None:
        indexed: dict[str, tuple[set[str], set[str]]] = {}
        volumes_by_syllable: dict[str, set[str]] = defaultdict(set)
        clusters_by_syllable: dict[str, set[str]] = defaultdict(set)
        for item in read(
            ROOT / "data/tibetan_latin_canonical_teaching_evidence.tsv"
        ):
            if (
                item["canonical_teaching_status"]
                != "independent_teaching_evidence"
            ):
                continue
            syllable = item["tibetan_syllable"]
            volumes_by_syllable[syllable].add(item["volume"])
            clusters_by_syllable[syllable].add(
                f"{item['volume']}:{item['page']}"
            )
        for syllable in volumes_by_syllable.keys() | clusters_by_syllable.keys():
            indexed[syllable] = (
                volumes_by_syllable[syllable],
                clusters_by_syllable[syllable],
            )
        _TEACHING_DIVERSITY_CACHE = indexed
    volumes: set[str] = set()
    clusters: set[str] = set()
    for syllable in syllables:
        syllable_volumes, syllable_clusters = _TEACHING_DIVERSITY_CACHE.get(
            syllable, (set(), set())
        )
        volumes.update(syllable_volumes)
        clusters.update(syllable_clusters)
    return volumes, clusters


def empirical_rule_qualifies(
    rule: dict[str, str], excluded_syllable: str = "",
) -> bool:
    syllables = _supporting_syllables(rule, excluded_syllable)
    pairs = [
        item for item in _pair_items(rule)
        if not excluded_syllable
        or f"{excluded_syllable}:" not in item
    ]
    volumes, clusters = _support_diversity(syllables)
    evidence_kinds = set(rule.get("evidence_kind", "").split(";"))
    residual = "single_unknown_residual_induction" in evidence_kinds
    return (
        len(syllables) >= (4 if residual else 3)
        and (len(syllables) >= 3 if residual else len(pairs) >= 2)
        and len(volumes) >= 2
        and len(clusters) >= 2
        and not rule.get("competing_realizations", "")
        and (
            residual
            or bool(evidence_kinds & {
                "full_realization_isolated", "zero_realization_isolated"
            })
        )
    )


def strict_rule_available(
    rule: dict[str, str], excluded_syllable: str,
) -> bool:
    if rule.get("authority_basis") == "explicit_review":
        return True
    return empirical_rule_qualifies(rule, excluded_syllable)


def target_support_channel(
    syllable: str,
    target: str,
    teaching_rows: list[dict[str, str]],
    *,
    feature_complete: bool,
) -> tuple[str, bool]:
    """Return the strongest admissible observation channel for a target.

    A known OCR source, superseded target, probable alignment, or foreign-only
    observation is deliberately not positive ordinary-Tibetan target support.
    A derived target may support continued use only when the target is also
    independently feature-complete under strict leave-one-out.
    """
    matching = [
        row for row in teaching_rows
        if row["tibetan_syllable"] == syllable and row["latin_form"] == target
    ]
    statuses = {row["canonical_teaching_status"] for row in matching}
    domains = {row["domain_context"] for row in matching}
    if "reviewed_full_target_teaching_evidence" in statuses:
        return "reviewed_full_target", True
    if "independent_teaching_evidence" in statuses:
        return "secure_independent_observation", True
    if "supporting_but_derived" in statuses and feature_complete:
        return "derived_target_plus_independent_feature_composition", True
    if statuses == {"alternate_witness_only"}:
        return "alternate_witness_only", False
    if matching and domains <= {
        "sanskrit_or_indic_transcription",
        "chinese_or_other_foreign_transcription",
    }:
        return "foreign_domain_only", False
    if matching:
        return "nonadmissible_observation", False
    return "no_positive_target_observation", False


def build_sign_inventory(
    syllables: set[str],
    teaching_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    domains: dict[str, set[str]] = defaultdict(set)
    for row in teaching_rows:
        domains[row["tibetan_syllable"]].add(row["domain_context"])
    occurrences: Counter[str] = Counter()
    sign_syllables: dict[str, set[str]] = defaultdict(set)
    sign_domains: dict[str, set[str]] = defaultdict(set)
    for syllable in syllables:
        for char in unicodedata.normalize("NFC", syllable):
            occurrences[char] += 1
            sign_syllables[char].add(syllable)
            sign_domains[char].update(domains.get(syllable, {"unknown"}))
    rows = []
    for char in sorted(occurrences, key=ord):
        sign_class, treatment, safe = classify_tibetan_sign(char)
        rows.append({
            "code_point": f"U+{ord(char):04X}",
            "unicode_name": unicodedata.name(char, "UNKNOWN"),
            "sign_class": sign_class,
            "syllable_count": str(len(sign_syllables[char])),
            "occurrence_count": str(occurrences[char]),
            "domains": ";".join(sorted(sign_domains[char])),
            "sample_syllables": ";".join(sorted(sign_syllables[char])[:20]),
            "parser_treatment": treatment,
            "composition_safe": "yes" if safe else "no",
        })
    return rows


def build_revalidation(
    candidates: list[dict[str, str]],
) -> list[dict[str, str]]:
    candidate_by_id = {row["rule_id"]: row for row in candidates}
    rows: list[dict[str, str]] = []
    for decision in read(DECISIONS_PATH):
        candidate = candidate_by_id.get(decision["rule_id"], {})
        basis = (
            "empirical_corpus"
            if decision.get("provenance", "").startswith("corpus_internal_")
            else "explicit_review"
        )
        supporters = _supporting_syllables(candidate)
        volumes, clusters = _support_diversity(supporters)
        held_out_counts = [
            len(_supporting_syllables(candidate, syllable))
            for syllable in supporters
            if strict_rule_available(
                {**candidate, "authority_basis": basis}, syllable
            )
        ]
        effective = (
            decision["decision"] == "A"
            and (
                basis == "explicit_review"
                or empirical_rule_qualifies(candidate)
            )
        )
        rows.append({
            "rule_id": decision["rule_id"], "authority_basis": basis,
            "historical_decision": decision["decision"],
            "original_supporting_syllables":
                candidate.get("strong_canonical_syllables", ""),
            "current_qualifying_syllables":
                candidate.get("strong_canonical_syllables", "")
                if effective else "",
            "current_qualifying_contrasts": str(len(_pair_items(candidate))),
            "current_volumes": ";".join(sorted(volumes)),
            "current_entry_clusters": ";".join(sorted(clusters)),
            "conflicts": candidate.get("competing_realizations", ""),
            "evidence_kind": candidate.get("evidence_kind", ""),
            "strict_leave_one_out_minimum_support": (
                str(min(held_out_counts)) if held_out_counts else "0"
            ),
            "dependency_status": "current" if candidate else "missing_candidate",
            "effective_authority": "yes" if effective else "no",
            "rationale": (
                "Empirical A decisions remain usable only while complete-role "
                "evidence, three syllables, two contrasts, two volumes, two "
                "clusters, and zero competition remain current."
            ),
        })
    return rows


def isolate_single_unknown_residual(
    parse: dict[str, str],
    target: str,
    rules: dict[tuple[str, str], dict[str, str]],
    syllable: str,
) -> tuple[str, str, str, list[str], str]:
    """Isolate one complete unknown role span using anchored known neighbours."""
    if parse["role_parse_status"] != "fully_resolved":
        return "", "", "", [], "role_parse_unresolved"
    present = [(role, parse[role]) for role in ROLE_ORDER if parse[role]]
    missing = [
        (index, role, feature)
        for index, (role, feature) in enumerate(present)
        if (role, feature) not in rules
        or not strict_rule_available(rules[(role, feature)], syllable)
    ]
    if len(missing) != 1:
        return "", "", "", [], (
            "multiple_unknown_roles" if len(missing) > 1
            else "no_unknown_role"
        )
    unknown_index, unknown_role, unknown_feature = missing[0]
    left_cursor = 0
    dependencies: list[str] = []
    for role, feature in present[:unknown_index]:
        rule = rules[(role, feature)]
        realization = rule["latin_realization"]
        if not target.startswith(realization, left_cursor):
            return "", "", "", dependencies, "left_anchor_mismatch"
        left_cursor += len(realization)
        dependencies.append(rule["rule_id"])
    right_cursor = len(target)
    for role, feature in reversed(present[unknown_index + 1:]):
        rule = rules[(role, feature)]
        realization = rule["latin_realization"]
        start = right_cursor - len(realization)
        if start < left_cursor or target[start:right_cursor] != realization:
            return "", "", "", dependencies, "right_anchor_mismatch"
        right_cursor = start
        dependencies.append(rule["rule_id"])
    residual = target[left_cursor:right_cursor]
    if left_cursor > right_cursor:
        return "", "", "", dependencies, "overlapping_anchors"
    return (
        unknown_role, unknown_feature, residual, dependencies,
        "single_unknown_residual_isolated",
    )


def build_residual_expansion(
    canonical: list[dict[str, str]],
    parses: dict[str, dict[str, str]],
    rules: dict[tuple[str, str], dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    grouped: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    blockers: Counter[tuple[str, str]] = Counter()
    canonical_by_syllable = {
        row["tibetan_syllable"]: row for row in canonical
    }
    for row in canonical:
        syllable = row["tibetan_syllable"]
        role, feature, residual, _deps, status = isolate_single_unknown_residual(
            parses[syllable], row["canonical_forms"], rules, syllable
        )
        if status == "single_unknown_residual_isolated":
            grouped[(role, feature, residual)].add(syllable)
        else:
            blockers[(status, "")] += 1
    teaching = read(
        ROOT / "data/tibetan_latin_canonical_teaching_evidence.tsv"
    )
    rows: list[dict[str, str]] = []
    by_feature: dict[tuple[str, str], set[str]] = defaultdict(set)
    for (role, feature, residual), supporters in sorted(grouped.items()):
        volumes, clusters = _support_diversity(supporters)
        by_feature[(role, feature)].add(residual)
        status = (
            "promotion_candidate"
            if len(supporters) >= 3 and len(volumes) >= 2
            and len(clusters) >= 2 else "provisional"
        )
        rows.append({
            "tibetan_role": role, "tibetan_feature": feature,
            "structural_context": "single_unknown_residual_induction",
            "strong_canonical_missing_count": str(len(supporters)),
            "single_unknown_count": str(len(supporters)),
            "isolated_residual_realizations": residual,
            "supporting_syllables": ";".join(sorted(supporters)),
            "supporting_volumes": ";".join(sorted(volumes)),
            "supporting_entry_clusters": ";".join(sorted(clusters)),
            "provisional_syllables_unlocked": "0",
            "secure_outliers_unlocked": "0",
            "final_ng_rows_unlocked": "0",
            "induction_status": status,
            "blocker": "none",
        })
    for row in rows:
        alternatives = by_feature[
            (row["tibetan_role"], row["tibetan_feature"])
        ]
        if len(alternatives) > 1:
            row["induction_status"] = "competing_residual_realizations"
            row["blocker"] = ";".join(sorted(alternatives))

    structural: list[dict[str, str]] = []
    # The common g+y separator is represented generically as a structural
    # interaction candidate, not silently repaired by independent role rules.
    gy_support = {
        row["tibetan_syllable"] for row in canonical
        if parses[row["tibetan_syllable"]].get("prefix") == "ག"
        and parses[row["tibetan_syllable"]].get("root_consonant") == "ཡ"
        and row["canonical_forms"].startswith("g.y")
    }
    if gy_support:
        volumes, _clusters = _support_diversity(gy_support)
        structural.append({
            "structural_unit": "prefix_root_cluster",
            "tibetan_context": "prefix:ག+root:ཡ",
            "latin_realization": "g.y",
            "supporting_syllables": ";".join(sorted(gy_support)),
            "supporting_volumes": ";".join(sorted(volumes)),
            "counterexamples": "",
            "evidence_kind": "structural_interaction_full_form_support",
            "recommendation": (
                "promotion_candidate" if len(gy_support) >= 3
                and len(volumes) >= 2 else "provisional"
            ),
        })
    return rows, structural


def simulate_expansion_yields(
    expansion: list[dict[str, str]],
    parses: dict[str, dict[str, str]],
    rules: dict[tuple[str, str], dict[str, str]],
    composition: list[dict[str, str]],
    teaching: list[dict[str, str]],
) -> None:
    """Populate downstream-yield columns by temporary, non-writing rules."""
    current = {row["tibetan_syllable"]: row for row in composition}
    outlier_path = ROOT / "data/tibetan_latin_transcription_outliers.tsv"
    outliers = read(outlier_path) if outlier_path.exists() else []
    final_rows: list[dict[str, str]] = []
    for path in (ROOT / "release/current/qa").glob(
        "wts_*/tibetan_cleanup_diagnostics/"
        "tibetan_final_ng_source_compatible_candidates.tsv"
    ):
        final_rows.extend(read(path))
    for row in expansion:
        realizations = [
            value for value in row["isolated_residual_realizations"].split(";")
            if value
        ]
        if len(realizations) != 1 or row["induction_status"] == (
            "competing_residual_realizations"
        ):
            continue
        role, feature = row["tibetan_role"], row["tibetan_feature"]
        if (role, feature) in rules:
            continue
        temporary = dict(rules)
        temporary[(role, feature)] = {
            "rule_id": f"SIMULATED:{role}:{feature}",
            "tibetan_role": role,
            "tibetan_feature": feature,
            "latin_realization": realizations[0],
            "structural_context": row["structural_context"],
        }
        newly_complete: dict[str, str] = {}
        newly_authoritative: set[str] = set()
        for syllable, parse in parses.items():
            if current.get(syllable, {}).get("feature_composed_target"):
                continue
            predicted, _ids, missing = compose(
                parse, temporary, excluded_syllable=syllable
            )
            if not predicted or missing:
                continue
            newly_complete[syllable] = predicted
            _channel, support_ok = target_support_channel(
                syllable, predicted, teaching, feature_complete=True
            )
            if support_ok:
                newly_authoritative.add(syllable)
        secure_outliers = sum(
            int(item.get("occurrence_count", "0") or 0)
            for item in outliers
            if item["tibetan_syllable"] in newly_authoritative
            and item.get("source_alignment_status")
            == "secure_transcription_outlier"
            and item.get("canonical_forms")
            == newly_complete[item["tibetan_syllable"]]
        )
        final_unlocked = sum(
            1 for item in final_rows
            if item["tibetan_syllable"] in newly_authoritative
            and item.get("proposed_latin_target")
            == newly_complete[item["tibetan_syllable"]]
        )
        row["provisional_syllables_unlocked"] = str(len(newly_complete))
        row["secure_outliers_unlocked"] = str(secure_outliers)
        row["final_ng_rows_unlocked"] = str(final_unlocked)


def residual_mapping_candidates(
    expansion: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    decisions = {
        (
            row["tibetan_role"], row["tibetan_feature"],
            row["latin_realization"],
        ): row
        for row in read(DECISIONS_PATH)
    }
    for item in expansion:
        realization = item["isolated_residual_realizations"]
        key = (
            item["tibetan_role"], item["tibetan_feature"], realization
        )
        digest = hashlib.sha1(
            "\u241f".join(key).encode("utf-8")
        ).hexdigest()[:12].upper()
        decision = decisions.get(key, {})
        rows.append({
            "rule_id": decision.get("rule_id", f"RESIDUAL_{digest}"),
            "tibetan_role": item["tibetan_role"],
            "tibetan_feature": item["tibetan_feature"],
            "structural_context": "single_unknown_residual_induction",
            "contrastive_delta": "",
            "evidence_kind": "single_unknown_residual_induction",
            "full_role_realization_candidate": realization,
            "proposed_latin_realization": realization,
            "strong_canonical_syllables": item["supporting_syllables"],
            "independent_feature_evidence_identities": "",
            "reviewed_explicit_support": "0",
            "unaffected_reviewed_source_support": "0",
            "minimal_pair_support": "",
            "alternate_witness_support": "0",
            "supporting_volumes": item["supporting_volumes"],
            "supporting_entry_clusters":
                item["supporting_entry_clusters"],
            "counterexamples": "",
            "competing_realizations": (
                item["blocker"] if item["induction_status"]
                == "competing_residual_realizations" else ""
            ),
            "domain_breakdown":
                "ordinary_tibetan_lexical_or_compound",
            "confidence": (
                "high" if item["induction_status"] == "promotion_candidate"
                else "provisional"
            ),
            "recommendation": (
                "feature_independent_strong_candidate"
                if item["induction_status"] == "promotion_candidate"
                else "feature_provisional"
            ),
        })
    return rows


def merge_mapping_candidates(
    contrast: list[dict[str, str]],
    residual: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Prefer complete residual evidence when a historical rule ID overlaps."""
    merged = {row["rule_id"]: row for row in contrast}
    for row in residual:
        existing = merged.get(row["rule_id"])
        if (
            not existing
            or row["evidence_kind"] == "single_unknown_residual_induction"
        ):
            merged[row["rule_id"]] = row
    return list(merged.values())


def build_correction_authority_backaudit(
    composition: list[dict[str, str]],
    dependencies: list[dict[str, str]],
    role_spans: list[dict[str, str]],
) -> list[dict[str, str]]:
    shadow = {
        (row["volume"], row["page"], row["line"], row["token_index"]): row
        for row in read(SOURCE_SHADOW_PATH)
    }
    canonical = {
        row["tibetan_syllable"]: row for row in read(CANONICAL_PATH)
    }
    composed = {row["tibetan_syllable"]: row for row in composition}
    dependency = {row["tibetan_syllable"]: row for row in dependencies}
    spans_by_target: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for span in role_spans:
        spans_by_target[(span["tibetan_syllable"], span["target"])].append(span)
    diagnostics = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in integrity.build_diagnostics(ROOT / "release/current")
    }
    aligned_current = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in integrity.collect_all_aligned(ROOT / "release/current")
    }
    scope_registry = {
        r["reason"]: r
        for r in read(ROOT / "data/reviewed_correction_evidence_scopes.tsv")
    }
    snapshot = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    rows: list[dict[str, str]] = []
    for override in read(integrity.OVERRIDES_PATH):
        key = tuple(
            override[field]
            for field in ("volume", "page", "line", "token_index")
        )
        source = shadow.get(key, {})
        registered_scope = scope_registry.get(override["reason"], {}).get(
            "evidence_scope", ""
        )
        effective_scope = source.get("evidence_scope") or registered_scope
        if effective_scope not in {
            "derived_from_existing_canonical", "composed_repair",
        } and override["reason"] != "reviewed_tibetan_exact_ocr_signature":
            continue
        syllable = (
            source.get("tibetan_syllable", "")
            or aligned_current.get(key, {}).get("tibetan_syllable", "")
        )
        current_composition = composed.get(syllable, {})
        canonical_row = canonical.get(syllable, {})
        dependency_row = dependency.get(syllable, {})
        target_authority = canonical_row.get(
            "canonical_confidence_tier", "unknown"
        )
        operations = changed_spans(
            override["from_token"], override["to_token"]
        )
        signatures = ";".join(
            f"{item['operation_type']}:{item['source_span']}→"
            f"{item['target_span']}"
            for item in operations
        )
        retained = (
            target_authority in {
                "canonical_reviewed", "canonical_independent_strong"
            }
            or (
                current_composition.get("correction_authority") == "yes"
                and current_composition.get("feature_composed_target")
                == override["to_token"]
            )
        )
        exact_canonical_route = target_authority in {
            "canonical_reviewed", "canonical_independent_strong"
        }
        target_spans = spans_by_target.get((syllable, override["to_token"]), [])
        locations: list[str] = []
        for operation in operations:
            target_start = int(operation.get("target_position", "0") or 0)
            target_end = target_start + len(operation.get("target_span", ""))
            if not operation.get("target_span"):
                source_position = int(operation.get("source_position", "0"))
                if source_position == 0:
                    locations.append("extra_source_material:token_initial")
                elif source_position + len(operation.get("source_span", "")) \
                        == len(override["from_token"]):
                    locations.append("extra_source_material:token_final")
                else:
                    locations.append("extra_source_material:internal")
                continue
            matching = [
                span for span in target_spans
                if (
                    target_start < int(span["target_end"])
                    and target_end > int(span["target_start"])
                )
                or (
                    target_start == target_end
                    and int(span["target_start"]) <= target_start
                    <= int(span["target_end"])
                )
            ]
            locations.append(
                ",".join(
                    f"{span['tibetan_role']}:{span['tibetan_feature']}"
                    for span in matching
                ) or "extra_or_unresolved"
            )
        diagnostic = diagnostics.get(key, {})
        current_status = (
            "current_authority_retained" if retained else
            "authority_downgraded_correction_preserved"
        )
        rows.append({
            "volume": override["volume"], "page": override["page"],
            "line": override["line"],
            "token_index": override["token_index"],
            "tibetan_syllable": syllable,
            "source": override["from_token"], "target": override["to_token"],
            "target_authority_at_correction": target_authority,
            "component_feature_rules": (
                canonical_row.get("feature_dependency_rule_ids", "")
                or current_composition.get("component_rule_ids", "")
            ),
            "self_contribution": dependency_row.get(
                "target_in_rule_evidence", "not_in_current_dependency_audit"
            ),
            "strict_leave_one_out_status": current_composition.get(
                "leave_one_out_status", "insufficient"
            ) if not exact_canonical_route else "exact_canonical_route",
            "ocr_signatures": signatures,
            "domain_authority": (
                "proper_name_reviewed" if "thang" in override["evidence"]
                else "ordinary_tibetan"
            ),
            "prior_exact_decision": "none_before_active_override",
            "present_source_status": source.get(
                "source_disposition", "reviewed_source_shadow_missing"
            ),
            "present_target_status": (
                current_composition.get("composition_status")
                or target_authority
            ),
            "backaudit_disposition": current_status,
            # Extended persistent authority-provenance fields.
            "observed_source": override["from_token"],
            "correction_reason": override["reason"],
            "evidence_label": override["evidence"],
            "correction_batch": override["evidence"],
            "correction_commit": "",
            "target_authority_at_decision": target_authority,
            "canonical_target": canonical_row.get("canonical_forms", ""),
            "component_feature_rule_ids": (
                canonical_row.get("feature_dependency_rule_ids", "")
                or current_composition.get("component_rule_ids", "")
            ),
            "structural_unit_rule_ids": dependency_row.get(
                "structural_unit_dependencies", ""
            ),
            "strict_leave_one_out_result": current_composition.get(
                "leave_one_out_status", "exact_canonical_route"
            ),
            "target_support_channel": dependency_row.get(
                "target_support_channel", ""
            ),
            "ocr_signature_ids": signatures,
            "edit_structural_locations": ";".join(locations),
            "gate0_alignment_status": diagnostic.get(
                "alignment_confidence", "reviewed_exact_identity"
            ),
            "token_boundary_status": diagnostic.get(
                "token_boundary_status", "reviewed_exact_identity"
            ),
            "domain_gate": diagnostic.get(
                "domain_context", "reviewed_exact_identity"
            ),
            "prior_exact_decision_status": "none_before_active_override",
            "authority_snapshot_sha": snapshot,
            "current_backaudit_status": current_status,
        })
    return rows


def build_unaffected_source_recovery(
    parses: dict[str, dict[str, str]],
    rules: dict[tuple[str, str], dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    audit: list[dict[str, str]] = []
    recovered_evidence: list[dict[str, str]] = []
    for source in read(SOURCE_SHADOW_PATH):
        if source["unaffected_source_may_teach"] != "yes":
            continue
        syllable = source["tibetan_syllable"]
        parse = parses.get(syllable, {})
        operations = changed_spans(
            source["observed_source"], source["reviewed_target"]
        )
        corrected_roles = {
            item for item in source["corrected_tibetan_roles"].split(";")
            if item
        }
        recovered: list[tuple[str, str, str, str]] = []
        dependencies: list[str] = []
        cursor = 0
        blocker = ""
        if parse.get("role_parse_status") != "fully_resolved":
            blocker = parse.get("role_parse_status", "parse_missing")
        else:
            for role in ROLE_ORDER:
                feature = parse.get(role, "")
                if not feature:
                    continue
                if role in corrected_roles:
                    matching = [
                        op for op in operations
                        if int(op["source_position"]) == cursor
                    ]
                    if len(matching) != 1:
                        blocker = f"corrected_span_not_isolated:{role}"
                        break
                    cursor += len(matching[0]["source_span"])
                    continue
                rule = rules.get((role, feature))
                if not rule or not strict_rule_available(rule, syllable):
                    blocker = f"mapping_unavailable:{role}:{feature}"
                    break
                realization = rule["latin_realization"]
                end = cursor + len(realization)
                if source["observed_source"][cursor:end] != realization:
                    blocker = f"source_span_mismatch:{role}:{feature}"
                    break
                recovered.append(
                    (role, feature, realization, rule["rule_id"])
                )
                dependencies.append(rule["rule_id"])
                cursor = end
            if not blocker and cursor != len(source["observed_source"]):
                blocker = "unexplained_source_tail"
        if not blocker and recovered:
            recovery_status = "role_specific_unaffected_evidence"
            structural_unit = "none"
            for role, feature, realization, rule_id in recovered:
                recovered_evidence.append({
                    "volume": source["volume"], "page": source["page"],
                    "line": source["line"],
                    "token_index": source["token_index"],
                    "tibetan_syllable": syllable,
                    "latin_source": source["observed_source"],
                    "latin_target": source["reviewed_target"],
                    "tibetan_role": role, "tibetan_feature": feature,
                    "latin_realization": realization,
                    "structural_unit": f"resolved_{role}_span",
                    "evidence_provenance": (
                        source["correction_reason"]
                        + "|segmentation_dependency:" + rule_id
                    ),
                    "source_or_target": "source",
                    "independence_class": "historical_source",
                    "feature_teaching_status":
                        "unaffected_role_evidence_from_reviewed_source",
                    "domain": "", "alignment": "secure_reviewed_alignment",
                    "confidence": "high",
                })
        elif (
            parse.get("role_parse_status") == "fully_resolved"
            and corrected_roles == {"suffix_coda"}
            and operations
            and all(
                int(op["source_position"]) + len(op["source_span"])
                == len(source["observed_source"])
                for op in operations
            )
        ):
            recovery_status = "pre_coda_structural_unit_evidence"
            structural_unit = source["observed_source"][
                :int(operations[0]["source_position"])
            ]
        else:
            recovery_status = "masked_unsegmented_unaffected_span"
            structural_unit = ""
        audit.append({
            "volume": source["volume"], "page": source["page"],
            "line": source["line"], "token_index": source["token_index"],
            "tibetan_syllable": syllable,
            "observed_source": source["observed_source"],
            "reviewed_target": source["reviewed_target"],
            "source_disposition": source["source_disposition"],
            "corrected_roles": source["corrected_tibetan_roles"],
            "recovery_status": recovery_status,
            "recovered_roles": ";".join(item[0] for item in recovered),
            "structural_unit": structural_unit,
            "mapping_dependencies": ";".join(dependencies),
            "blocker": blocker or "none",
        })
    return audit, recovered_evidence


def compose(
    parse: dict[str, str],
    rules: dict[tuple[str, str], dict[str, str]],
    *,
    excluded_syllable: str = "",
    candidates: list[dict[str, str]] | None = None,
) -> tuple[str, list[str], list[str]]:
    spans: list[str] = []
    rule_ids: list[str] = []
    missing: list[str] = []
    if parse["role_parse_status"] != "fully_resolved":
        return "", [], ["orthographic_role_unresolved"]
    # The corpus writes an explicit separator for the resolved ག + ཡ onset
    # (for example g.yo).  Independent role rules for g and y cannot silently
    # erase that cluster-conditioned punctuation.
    if parse["prefix"] == "ག" and parse["root_consonant"] == "ཡ":
        return "", [], ["cluster:ག+ཡ:conditioned_separator_unresolved"]
    if (
        parse["root_consonant"] == "ཐ"
        and parse["subjoined_consonants"]
    ):
        return "", [], [
            "cluster:root_ཐ+subjoined:structural_realization_unresolved"
        ]
    for role in ROLE_ORDER:
        feature = parse[role]
        if not feature:
            continue
        rule = rules.get((role, feature))
        if not rule:
            missing.append(f"{role}:{feature}")
            continue
        if excluded_syllable and not strict_rule_available(
            rule, excluded_syllable
        ):
            missing.append(f"{role}:{feature}:held_out_rule_insufficient")
            continue
        spans.append(rule["latin_realization"])
        rule_ids.append(rule["rule_id"])
    return "".join(spans) if not missing else "", rule_ids, missing


def compose_with_role_spans(
    parse: dict[str, str],
    rules: dict[tuple[str, str], dict[str, str]],
    *,
    excluded_syllable: str = "",
) -> tuple[str, list[dict[str, str]], list[str]]:
    """Compose while retaining exact Latin offsets for every Tibetan role."""
    target, _rule_ids, missing = compose(
        parse, rules, excluded_syllable=excluded_syllable
    )
    if not target:
        return "", [], missing
    spans: list[dict[str, str]] = []
    offset = 0
    for role in ROLE_ORDER:
        feature = parse.get(role, "")
        if not feature:
            continue
        rule = rules[(role, feature)]
        realization = rule["latin_realization"]
        end = offset + len(realization)
        spans.append({
            "tibetan_role": role,
            "tibetan_feature": feature,
            "target_start": str(offset),
            "target_end": str(end),
            "target_span": realization,
            "rule_id": rule["rule_id"],
            "structural_context": rule["structural_context"],
        })
        offset = end
    if offset != len(target):
        raise ValueError(
            f"Role-span coverage mismatch for {parse['tibetan_syllable']}"
        )
    return target, spans, []


def build() -> tuple[list[dict[str, str]], ...]:
    canonical = canonical_forms()
    syllables = {
        row["tibetan_syllable"] for row in read(CONCORDANCE_PATH)
    } | {row["tibetan_syllable"] for row in canonical}
    parse_rows = [parse_tibetan_syllable(s) for s in sorted(syllables)]
    parses = {row["tibetan_syllable"]: row for row in parse_rows}
    base_feature_evidence = feature_teaching_evidence(parses)
    contrast_candidates = contrastive_candidates(
        canonical, parses, base_feature_evidence
    )
    residual_candidates_by_id: dict[str, dict[str, str]] = {}
    candidates = list(contrast_candidates)
    rules = authoritative_rules(candidates)
    expansion: list[dict[str, str]] = []
    structural: list[dict[str, str]] = []
    convergence: list[dict[str, str]] = []
    previous_candidate_ids: set[str] = set()
    for iteration in range(1, 21):
        expansion, structural = build_residual_expansion(
            canonical, parses, rules
        )
        for candidate in residual_mapping_candidates(expansion):
            residual_candidates_by_id[candidate["rule_id"]] = candidate
        candidates = merge_mapping_candidates(
            contrast_candidates, list(residual_candidates_by_id.values())
        )
        new_rules = authoritative_rules(candidates)
        new_rule_ids = sorted(
            new_rules[key]["rule_id"]
            for key in set(new_rules) - set(rules)
        )
        candidate_ids = set(residual_candidates_by_id)
        new_candidate_ids = sorted(candidate_ids - previous_candidate_ids)
        converged = set(new_rules) == set(rules) and not new_candidate_ids
        convergence.append({
            "iteration": str(iteration),
            "effective_rule_count": str(len(new_rules)),
            "new_rule_ids": ";".join(new_rule_ids) or "none",
            "new_residual_candidate_ids":
                ";".join(new_candidate_ids) or "none",
            "authority_changed": "yes" if set(new_rules) != set(rules) else "no",
            "converged": "yes" if converged else "no",
        })
        previous_candidate_ids = candidate_ids
        if converged:
            rules = new_rules
            break
        rules = new_rules
    else:
        raise ValueError("Residual feature induction failed to converge")
    feature_evidence = feature_teaching_evidence(parses, rules)
    source_recovery, recovered_feature_evidence = (
        build_unaffected_source_recovery(parses, rules)
    )
    feature_evidence = [
        row for row in feature_evidence
        if row["feature_teaching_status"]
        != "unaffected_role_evidence_from_reviewed_source"
    ] + recovered_feature_evidence
    contrast_candidates = contrastive_candidates(
        canonical, parses, feature_evidence
    )
    candidates = merge_mapping_candidates(
        contrast_candidates, list(residual_candidates_by_id.values())
    )
    rules = authoritative_rules(candidates)
    teaching = read(
        ROOT / "data/tibetan_latin_canonical_teaching_evidence.tsv"
    )
    sign_inventory = build_sign_inventory(syllables, teaching)
    revalidation = build_revalidation(candidates)

    backtest: list[dict[str, str]] = []
    canonical_by_syllable = {r["tibetan_syllable"]: r for r in canonical}
    for row in canonical:
        parse = parses[row["tibetan_syllable"]]
        prediction, rule_ids, missing = compose(
            parse, rules, excluded_syllable=row["tibetan_syllable"],
            candidates=candidates,
        )
        held_out = any(
            "held_out_rule_insufficient" in item for item in missing
        )
        if prediction == row["canonical_forms"]:
            status = "exact_reconstruction"
        elif prediction:
            status = "wrong_prediction_blocked_by_exact_canonical"
        elif parse["role_parse_status"] == "unsupported_orthographic_sign":
            status = "unsupported_orthographic_sign"
        elif held_out:
            status = "exact_held_out_evidence_insufficient"
        elif parse["role_parse_status"] != "fully_resolved":
            status = "role_parse_unresolved"
        elif missing:
            status = "partial_reconstruction"
        else:
            status = "ambiguous"
        backtest.append({
            "tibetan_syllable": row["tibetan_syllable"],
            "hidden_canonical_target": row["canonical_forms"],
            "canonical_tier": row["canonical_confidence_tier"],
            "role_parse_status": parse["role_parse_status"],
            "prediction": prediction,
            "component_rule_ids": ";".join(rule_ids),
            "leave_one_out_status": (
                "passed" if prediction else
                "held_out_rule_insufficient" if held_out else "insufficient"
            ),
            "reconstruction_status": status,
            "missing_roles": ";".join(missing) or "none",
        })

    concordance_by_syllable: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read(CONCORDANCE_PATH):
        concordance_by_syllable[row["tibetan_syllable"]].append(row)
    composition: list[dict[str, str]] = []
    for syllable, forms in sorted(concordance_by_syllable.items()):
        existing = canonical_by_syllable.get(syllable)
        current_tier = (
            existing["canonical_confidence_tier"] if existing else next(
                (r["canonical_confidence_tier"] for r in read(CANONICAL_PATH)
                 if r["tibetan_syllable"] == syllable), "unresolved"
            )
        )
        prediction, rule_ids, missing = compose(
            parses[syllable], rules, excluded_syllable=syllable,
            candidates=candidates,
        )
        exact_canonical_conflict = bool(
            prediction and existing
            and existing["canonical_confidence_tier"] in {
                "canonical_reviewed", "canonical_independent_strong"
            }
            and existing["canonical_forms"] != prediction
        )
        support_channel, support_ok = target_support_channel(
            syllable, prediction, teaching, feature_complete=bool(prediction)
        ) if prediction else ("no_feature_target", False)
        if exact_canonical_conflict:
            status, authority, blocker = (
                "known_canonical_conflict", "no",
                f"exact canonical {existing['canonical_forms']} != {prediction}",
            )
        elif prediction and support_ok:
            status, authority, blocker = (
                "feature_complete_unique", "yes", "none",
            )
        elif prediction:
            status, authority, blocker = (
                "feature_complete_target_support_insufficient", "no",
                support_channel,
            )
        elif parses[syllable]["role_parse_status"] != "fully_resolved":
            status, authority, blocker = (
                "role_parse_unresolved", "no",
                parses[syllable]["role_parse_status"],
            )
        else:
            status, authority, blocker = (
                "feature_partial", "no", ";".join(missing),
            )
        composition.append({
            "tibetan_syllable": syllable,
            "observed_forms": ";".join(r["latin_form"] for r in forms),
            "current_canonical_tier": current_tier,
            "role_parse_status": parses[syllable]["role_parse_status"],
            "composition_status": status,
            "feature_composed_target": prediction,
            "component_rule_ids": ";".join(rule_ids),
            "supporting_evidence_ids": support_channel,
            "leave_one_out_status": "passed" if prediction else "insufficient",
            "domain_compatibility": "ordinary_only",
            "correction_authority": authority,
            "blocker": blocker,
        })

    domain: list[dict[str, str]] = []
    canonical_targets = {
        row["tibetan_syllable"]: row["canonical_forms"]
        for row in canonical
    }
    for rule in rules.values():
        domain_support: dict[str, set[str]] = defaultdict(set)
        domain_conflicts: dict[str, set[str]] = defaultdict(set)
        for item in teaching:
            syllable = item["tibetan_syllable"]
            if item["latin_form"] != canonical_targets.get(syllable):
                continue
            parse = parses.get(syllable, {})
            role, feature = rule["tibetan_role"], rule["tibetan_feature"]
            if parse.get(role) != feature:
                continue
            predicted, _ids, missing = compose(parse, rules)
            if predicted == item["latin_form"]:
                domain_support[item["domain_context"]].add(syllable)
            elif predicted and not missing:
                domain_conflicts[item["domain_context"]].add(
                    f"{syllable}:{item['latin_form']}≠{predicted}"
                )
        proper_count = len(domain_support["tibetan_proper_name"])
        ordinary_count = len(
            domain_support["ordinary_tibetan_lexical_or_compound"]
        )
        domain.append({
            "rule_id": rule["rule_id"],
            "ordinary_lexical_support": str(ordinary_count),
            "proper_name_support": str(proper_count),
            "sanskrit_foreign_support": str(len(
                domain_support["sanskrit_or_indic_transcription"]
            )),
            "unclear_support": str(len(domain_support["unclear"])),
            "conflicts": ";".join(sorted(
                value for values in domain_conflicts.values()
                for value in values
            )),
            "proper_name_compatible": (
                "yes" if proper_count >= 3
                and not domain_conflicts["tibetan_proper_name"] else "no"
            ),
            "rationale": (
                "Proper-name compatibility requires the reviewed/strong exact "
                "canonical realization in at least three independent proper-name "
                "syllables; ordinary lexical authority is never inherited alone."
            ),
        })

    graph: list[dict[str, str]] = []
    for row in feature_evidence:
        graph.append({
            "from_node": "identity:" + identity(row),
            "from_node_type": "exact_observation",
            "edge_type": "supports",
            "to_node": (
                f"feature:{row['tibetan_role']}:{row['tibetan_feature']}:"
                f"{row['latin_realization']}"
            ),
            "to_node_type": "feature_rule_evidence",
            "evidence_identity": identity(row),
            "dependency_edge": "yes",
            "teaching_allowed": (
                "yes" if row["feature_teaching_status"] in {
                    "independent_full_form_feature_evidence",
                    "reviewed_explicit_feature_evidence",
                    "unaffected_feature_from_reviewed_source",
                } else "no"
            ),
        })
    for row in composition:
        if not row["feature_composed_target"]:
            continue
        for rule_id in row["component_rule_ids"].split(";"):
            graph.append({
                "from_node": "feature_rule:" + rule_id,
                "from_node_type": "feature_rule",
                "edge_type": "depends_on_rule",
                "to_node": "canonical_feature_composed:" + row["tibetan_syllable"],
                "to_node_type": "feature_composed_target",
                "evidence_identity": row["tibetan_syllable"],
                "dependency_edge": "yes",
                "teaching_allowed": "no",
            })
    validate_no_cycles(graph)
    orthography_audit: list[dict[str, str]] = []
    dependencies: list[dict[str, str]] = []
    migration: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    role_spans: list[dict[str, str]] = []
    old_composed = [
        row for row in read_git_tsv(
            FEATURE_COMPOSITION_AUDIT_BASELINE,
            "data/tibetan_latin_canonical_syllables.tsv",
        )
        if row["canonical_confidence_tier"] == "canonical_feature_composed"
    ]
    composition_by_syllable = {
        row["tibetan_syllable"]: row for row in composition
    }
    candidate_by_id = {row["rule_id"]: row for row in candidates}
    # Historical migration audit: the 429 baseline rows remain an immutable
    # comparison set, separate from current dependency completeness.
    for old in old_composed:
        syllable = old["tibetan_syllable"]
        current = composition_by_syllable.get(syllable, {})
        parse = parses[syllable]
        unsupported = unsupported_orthographic_signs(syllable)
        retain = (
            current.get("correction_authority") == "yes"
            and current.get("feature_composed_target")
            == old["canonical_forms"]
        )
        channel = current.get("supporting_evidence_ids", "")
        orthography_audit.append({
            "tibetan_syllable": syllable,
            "feature_composed_target": old["canonical_forms"],
            "tibetan_signs": ";".join(
                f"U+{ord(c):04X}" for c in syllable
            ),
            "parser_interpretation": parse["role_parse_status"],
            "component_rule_ids": current.get("component_rule_ids", ""),
            "domain": old["domain_breakdown"],
            "unsupported_sign_status": (
                ";".join(f"U+{ord(c):04X}" for c in unsupported)
                if unsupported else "none"
            ),
            "target_support_channel": channel,
            "retain_or_downgrade": "retain" if retain else "downgrade",
            "rationale": (
                "Current strict composition and admissible target support pass."
                if retain else current.get("blocker", "composition_changed")
            ),
        })
        migration.append({
            "tibetan_syllable": syllable,
            "baseline_target": old["canonical_forms"],
            "current_target": current.get("feature_composed_target", ""),
            "baseline_status": "canonical_feature_composed",
            "current_status": current.get("composition_status", "absent"),
            "migration_disposition": "retained" if retain else "downgraded",
            "rationale": (
                "Current strict composition matches the baseline target."
                if retain else current.get("blocker", "composition_changed")
            ),
        })

    canonical_registry = {
        row["tibetan_syllable"]: row for row in read(CANONICAL_PATH)
    }
    # Current dependencies iterate the current composition state—not the old
    # 429-row baseline.
    for current in composition:
        target = current.get("feature_composed_target", "")
        if not target:
            continue
        syllable = current["tibetan_syllable"]
        component_ids = [
            item for item in current.get("component_rule_ids", "").split(";")
            if item
        ]
        missing_rule_ids = [
            rule_id for rule_id in component_ids
            if rule_id not in candidate_by_id
        ]
        if missing_rule_ids:
            raise ValueError(
                f"Unknown composition rule(s) for {syllable}: "
                + ";".join(missing_rule_ids)
            )
        inactive_rule_ids = [
            rule_id for rule_id in component_ids
            if rule_id not in {r["rule_id"] for r in rules.values()}
        ]
        if inactive_rule_ids:
            raise ValueError(
                f"Inactive composition rule(s) for {syllable}: "
                + ";".join(inactive_rule_ids)
            )
        evidence_syllables = sorted({
            evidence_syllable
            for rule_id in component_ids
            for evidence_syllable in _supporting_syllables(
                candidate_by_id.get(rule_id, {})
            )
        })
        dependencies.append({
            "tibetan_syllable": syllable,
            "target": target,
            "component_rule_ids": ";".join(component_ids),
            "rule_evidence_syllables": ";".join(evidence_syllables),
            "target_in_rule_evidence": (
                "yes" if syllable in evidence_syllables else "no"
            ),
            "strict_leave_one_out_status":
                current.get("leave_one_out_status", "insufficient"),
            "structural_unit_dependencies": "",
            "domain_rule_dependencies":
                current.get("domain_compatibility", ""),
            "target_support_channel":
                current.get("supporting_evidence_ids", ""),
            "authority_status": (
                "correction_authoritative"
                if canonical_registry.get(syllable, {}).get(
                    "canonical_confidence_tier"
                ) == "canonical_feature_composed"
                and canonical_registry[syllable]["canonical_forms"] == target
                else "complete_not_currently_authoritative"
            ),
        })
        _target, spans, span_missing = compose_with_role_spans(
            parses[syllable], rules, excluded_syllable=syllable
        )
        if span_missing or _target != target:
            raise ValueError(f"Role spans disagree with composition for {syllable}")
        for span in spans:
            role_spans.append({
                "tibetan_syllable": syllable,
                "target": target,
                "target_authority": dependencies[-1]["authority_status"],
                **span,
                "domain_authority": current["domain_compatibility"],
            })

    # Reviewed/strong exact canonicals also expose spans when strict held-out
    # composition reconstructs them exactly.
    spanned_targets = {
        (row["tibetan_syllable"], row["target"]) for row in role_spans
    }
    for row in backtest:
        if row["reconstruction_status"] != "exact_reconstruction":
            continue
        key = (row["tibetan_syllable"], row["hidden_canonical_target"])
        if key in spanned_targets:
            continue
        _target, spans, missing = compose_with_role_spans(
            parses[row["tibetan_syllable"]], rules,
            excluded_syllable=row["tibetan_syllable"],
        )
        if missing or _target != row["hidden_canonical_target"]:
            continue
        for span in spans:
            role_spans.append({
                "tibetan_syllable": row["tibetan_syllable"],
                "target": _target,
                "target_authority": row["canonical_tier"],
                **span,
                "domain_authority": "ordinary_only",
            })

    for row in backtest:
        if row["reconstruction_status"] != (
            "wrong_prediction_blocked_by_exact_canonical"
        ):
            continue
        syllable = row["tibetan_syllable"]
        _target, spans, _missing = compose_with_role_spans(
            parses[syllable], rules, excluded_syllable=syllable
        )
        true = row["hidden_canonical_target"]
        divergence = next(
            (
                str(index) for index, (left, right)
                in enumerate(zip(_target, true)) if left != right
            ),
            str(min(len(_target), len(true))),
        )
        ids = row["component_rule_ids"].split(";")
        conflicts.append({
            "tibetan_syllable": syllable,
            "true_canonical": true,
            "predicted_form": _target,
            "component_rule_ids": row["component_rule_ids"],
            "parsed_roles": ";".join(
                f"{role}:{parses[syllable].get(role, '')}"
                for role in ROLE_ORDER if parses[syllable].get(role, "")
            ),
            "predicted_role_spans": ";".join(
                f"{s['tibetan_role']}[{s['target_start']}:{s['target_end']}]="
                f"{s['target_span']}" for s in spans
            ),
            "canonical_segmentation": "unresolved_at_first_divergence",
            "first_divergence": divergence,
            "contributing_rules": ";".join(ids),
            "likely_missing_interaction":
                "structural_interaction_unresolved",
            "rule_supporting_syllables": ";".join(sorted({
                item for rule_id in ids
                for item in _supporting_syllables(candidate_by_id[rule_id])
            })),
            "disposition":
                "block_context_retain_rules_outside_failed_interaction",
        })

    current_composed = {
        row["tibetan_syllable"]: row
        for row in canonical_registry.values()
        if row["canonical_confidence_tier"] == "canonical_feature_composed"
    }
    authoritative_dependencies = {
        row["tibetan_syllable"]: row for row in dependencies
        if row["authority_status"] == "correction_authoritative"
    }
    if set(current_composed) != set(authoritative_dependencies):
        missing = sorted(set(current_composed) - set(authoritative_dependencies))
        extra = sorted(set(authoritative_dependencies) - set(current_composed))
        raise ValueError(
            f"Feature dependency completeness failed: missing={missing} "
            f"extra={extra}"
        )
    for syllable, canonical_row in current_composed.items():
        if authoritative_dependencies[syllable]["target"] != (
            canonical_row["canonical_forms"]
        ):
            raise ValueError(f"Feature dependency target mismatch: {syllable}")
    expansion, structural = build_residual_expansion(canonical, parses, rules)
    simulate_expansion_yields(
        expansion, parses, rules, composition, teaching
    )
    correction_audit = build_correction_authority_backaudit(
        composition, dependencies, role_spans
    )
    for candidate in candidates:
        for syllable in _supporting_syllables(candidate):
            graph.append({
                "from_node": f"canonical:{syllable}",
                "from_node_type": "strong_or_reviewed_canonical",
                "edge_type": (
                    "induces_rule" if candidate["evidence_kind"]
                    == "single_unknown_residual_induction"
                    else "contrasts_with"
                ),
                "to_node": "feature_rule:" + candidate["rule_id"],
                "to_node_type": "feature_rule",
                "evidence_identity": syllable,
                "dependency_edge": "yes",
                "teaching_allowed": "yes",
            })
    for correction in correction_audit:
        correction_node = (
            "exact_correction:"
            f"{correction['volume']}:{correction['page']}:"
            f"{correction['line']}:{correction['token_index']}"
        )
        target_node = (
            "canonical_feature_composed:" + correction["tibetan_syllable"]
            if correction["target_authority_at_decision"]
            == "canonical_feature_composed"
            else "canonical:" + correction["tibetan_syllable"]
        )
        graph.append({
            "from_node": target_node,
            "from_node_type": "canonical_target",
            "edge_type": "produces_correction",
            "to_node": correction_node,
            "to_node_type": "exact_correction",
            "evidence_identity": (
                f"{correction['volume']}:{correction['page']}:"
                f"{correction['line']}:{correction['token_index']}"
            ),
            "dependency_edge": "yes",
            "teaching_allowed": "no",
        })
    validate_no_cycles(graph)
    return (
        parse_rows, feature_evidence, candidates, backtest, composition,
        domain, graph, sign_inventory, orthography_audit, revalidation,
        dependencies, expansion, structural, correction_audit,
        source_recovery, migration, conflicts, role_spans, convergence,
    )


def validate_no_cycles(graph: list[dict[str, str]]) -> None:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph:
        if edge.get("dependency_edge", edge.get("teaching_allowed")) == "yes":
            adjacency[edge["from_node"]].add(edge["to_node"])
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f"Transcription evidence cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for target in adjacency.get(node, set()):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in list(adjacency):
        visit(node)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    outputs = build()
    for name, rows, fields in [
        ("tibetan_orthographic_parse.tsv", outputs[0], PARSE_FIELDS),
        ("tibetan_latin_feature_teaching_evidence.tsv", outputs[1],
         FEATURE_EVIDENCE_FIELDS),
        ("tibetan_latin_role_mapping_candidates.tsv", outputs[2],
         MAPPING_FIELDS),
        ("tibetan_latin_feature_composition_backtest.tsv", outputs[3],
         BACKTEST_FIELDS),
        ("tibetan_latin_feature_composition_queue.tsv", outputs[4],
         COMPOSITION_FIELDS),
        ("tibetan_latin_domain_compatibility.tsv", outputs[5], DOMAIN_FIELDS),
        ("tibetan_transcription_evidence_graph.tsv", outputs[6], GRAPH_FIELDS),
        ("tibetan_orthographic_sign_inventory.tsv", outputs[7], SIGN_FIELDS),
        ("tibetan_latin_feature_composed_orthography_audit.tsv", outputs[8],
         ORTHOGRAPHY_AUDIT_FIELDS),
        ("tibetan_feature_mapping_revalidation.tsv", outputs[9],
         REVALIDATION_FIELDS),
        ("tibetan_feature_composition_dependencies.tsv", outputs[10],
         DEPENDENCY_FIELDS),
        ("tibetan_feature_mapping_expansion_queue.tsv", outputs[11],
         EXPANSION_FIELDS),
        ("tibetan_latin_structural_unit_candidates.tsv", outputs[12],
         STRUCTURAL_FIELDS),
        ("tibetan_latin_recent_feature_correction_backaudit.tsv", outputs[13],
         RECENT_CORRECTION_FIELDS),
        ("tibetan_latin_unaffected_source_evidence_audit.tsv", outputs[14],
         SOURCE_RECOVERY_FIELDS),
        ("tibetan_feature_composition_migration.tsv", outputs[15],
         MIGRATION_FIELDS),
        ("tibetan_feature_composition_conflicts.tsv", outputs[16],
         CONFLICT_FIELDS),
        ("tibetan_latin_canonical_role_spans.tsv", outputs[17],
         ROLE_SPAN_FIELDS),
        ("tibetan_transcription_correction_authority.tsv", outputs[13],
         CORRECTION_AUTHORITY_FIELDS),
        ("tibetan_feature_mapping_convergence.tsv", outputs[18],
         CONVERGENCE_FIELDS),
    ]:
        write(args.data_root / name, rows, fields)
    counts = Counter(r["role_parse_status"] for r in outputs[0])
    backtest = Counter(r["reconstruction_status"] for r in outputs[3])
    composition = Counter(r["composition_status"] for r in outputs[4])
    print(
        f"parses={dict(counts)} feature_evidence={len(outputs[1])} "
        f"mapping_candidates={len(outputs[2])} backtest={dict(backtest)} "
        f"composition={dict(composition)}"
    )


if __name__ == "__main__":
    main()
