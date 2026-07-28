#!/usr/bin/env python3
"""Build reviewed, non-circular OCR-signature evidence and action queues."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
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
    "signature_integrity", ROOT / "scripts/build_tibetan_latin_integrity.py"
)
canonical = load_module(
    "signature_canonical",
    ROOT / "scripts/build_tibetan_latin_syllable_concordance.py",
)

EVIDENCE_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "source", "target", "learning_class", "evidence_scope",
    "canonical_teaching_status", "operation_signatures", "operation_count",
    "domain", "reason", "evidence", "review_note", "history_status",
]
CONTROL_FIELDS = [
    "signature", "reviewed_positive_syllables", "reviewed_positive_occurrences",
    "historical_positive_occurrences", "alternate_witness_adopted",
    "alternate_witness_unresolved_or_candidate", "alternate_witness_conflicts",
    "legitimate_source_form_controls", "ambiguous_cases",
    "foreign_domain_cases", "alignment_noise_cases", "superseded_negative_count",
    "control_examples",
]
REGISTRY_FIELDS = [
    "signature_id", "operation_signature", "operation_type",
    "source_sequence", "target_sequence",
    "parent_signature", "tibetan_role", "tibetan_feature",
    "source_position_type", "source_position_value",
    "target_position_type", "target_position_value",
    "source_context_pattern",
    "target_context_pattern", "domain_condition",
    "source_structural_location", "target_structural_role",
    "parent_structural_unit", "crosses_role_boundaries",
    "extra_source_material", "forbidden_tibetan_roles",
    "forbidden_tibetan_features", "forbidden_tibetan_role_features",
    "canonical_target_required", "aligned_tibetan_required",
    "exact_tibetan_identities",
    "reviewed_atomic_supporting_syllables", "reviewed_supporting_occurrences",
    "reviewed_supporting_volumes", "reviewed_page_ranges",
    "historical_support", "alternate_witness_support",
    "legitimate_controls", "conflicts", "evidence_tier",
    "authorization_status", "rationale",
    "parent_operation_reviewed_support",
    "parent_operation_alternate_support", "parent_operation_global_controls",
    "conditioned_reviewed_support", "conditioned_alternate_support",
    "conditioned_controls", "conditioned_conflicts",
]
DECISION_FIELDS = [
    "signature", "role_domain_condition", "decision",
    "evidence_summary", "supporting_identities", "control_identities",
    "review_provenance", "date_batch",
]
QUEUE_FIELDS = [
    "tibetan_syllable", "current_source", "canonical_target",
    "canonical_confidence_tier", "occurrence_count", "edit_signatures",
    "signature_statuses", "action_category", "source_alignment_status",
    "domain_breakdown",
    "damage_or_marker", "boundary_secure_occurrences",
    "condition_matching_occurrences", "condition_failing_occurrences",
    "canonical_evidence", "target_authority_ready", "ocr_signature_ready",
    "alignment_ready", "boundary_ready", "domain_ready",
    "prior_decision_ready", "final_action_ready", "sample_contexts",
]
EXHAUSTION_FIELDS = [
    "signature", "remaining_outlier_families", "remaining_outlier_rows",
    "authoritative_target_rows", "clean_domain_safe_rows",
    "ready_uncorrected_rows", "disposition", "examples",
]
INCOMPLETE_FIELDS = [
    "tibetan_syllable", "active_target", "applied_target_count",
    "canonical_confidence_tier", "historical_occurrences",
    "independent_teaching_occurrences", "competing_forms",
    "promotion_disposition",
]
MODERATE_FIELDS = [
    "tibetan_syllable", "candidate_forms", "independent_occurrences",
    "volumes", "entry_clusters", "historical_occurrences",
    "competing_forms", "missing_evidence", "promotion_disposition",
]
PACKET_FIELDS = [
    "signature", "expected_clean_yield", "expected_syllable_yield",
    "reviewed_support", "alternate_witness_support",
    "global_source_controls", "gated_collision_controls",
    "same_tibetan_competing_controls", "domain_controls",
    "tibetan_syllable", "source", "canonical_target", "target_evidence",
    "volume", "page", "line", "token_index", "full_captured_source",
    "preceding_character", "following_character", "boundary_status",
    "operation_positions", "source_edit_start", "source_edit_end",
    "target_edit_start", "target_edit_end", "source_structural_location",
    "target_structural_role", "tibetan_role", "tibetan_feature",
    "parent_structural_unit", "target_component_rule_id",
    "crosses_role_boundaries", "extra_source_material",
    "edit_specific_domain_condition", "proposed_structural_role",
    "primitive_edit_sequence", "authorized_components",
    "missing_components", "compound_classification",
    "exact_alternate_witness_status", "exact_alternate_witness_token",
    "domain", "context", "suggested_decision",
]
EDIT_ATTRIBUTION_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable", "source",
    "canonical_target", "source_alignment_status", "boundary_status",
    "domain", "damage_or_marker", "operation_signature",
    "source_edit_start", "source_edit_end", "target_edit_start",
    "target_edit_end", "source_structural_location",
    "target_structural_role", "tibetan_role", "tibetan_feature",
    "parent_structural_unit", "target_component_rule_id",
    "crosses_role_boundaries", "extra_source_material",
    "edit_specific_domain_condition", "attribution_status",
]
ALIGNMENT_RESCUE_FIELDS = [
    "tibetan_syllable", "source", "canonical_target", "occurrence_count",
    "current_alignment_status", "rescue_category", "layout_evidence",
    "canonical_agreement_diagnostic_only", "upgrade_authorized", "blocker",
    "sample_contexts",
]
ALIGNMENT_RESCUE_EXACT_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable", "source",
    "canonical_target", "current_alignment_status", "rescue_category",
    "line_zone", "tibetan_token_ordinal", "latin_token_ordinal",
    "token_start", "token_end", "boundary_status", "damage_scope",
    "marker_attached", "layout_signature", "positive_layout_support",
    "negative_layout_collisions", "upgrade_authorized", "blocker",
    "context_excerpt",
]
ACTIVE_QUEUE_SUMMARY_FIELDS = [
    "queue_category", "family_count", "current_family_count",
    "current_exact_occurrences", "historical_only_families",
]
FINAL_NG_ACTIVE_SUMMARY_FIELDS = [
    "effective_disposition", "historical_diagnostic_rows",
    "current_extant_source_rows", "historical_only_rows",
    "current_target_ready_rows", "current_signature_ready_rows",
    "current_alignment_ready_rows", "current_domain_ready_rows",
    "current_final_action_ready_rows",
]
STRUCTURAL_ALTERNATE_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "source", "alternate_token", "canonical_target", "target_authority",
    "operation_signature", "signature_child_id", "witness_type",
    "alternate_relation", "condition_result", "unrelated_edits",
    "source_structural_location", "target_structural_role",
    "tibetan_role", "tibetan_feature", "parent_structural_unit",
]
STRUCTURAL_CHILD_EVIDENCE_FIELDS = [
    "signature_child_id", "parent_operation", "decision",
    "current_exact_rows", "distinct_syllables", "reviewed_support",
    "exact_alternate_support", "same_tibetan_independent_target_support",
    "source_volumes", "source_page_ranges", "line_zones",
    "parent_reviewed_support", "parent_alternate_support",
    "global_source_controls", "structural_gate_controls",
    "same_tibetan_competing_controls", "domain_controls",
    "reviewed_contradictions", "disposition",
]


def reconcile_correction_authority(
    registry_rows: list[dict[str, str]],
    aligned_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[str]]:
    """Backaudit historical exact corrections with the live condition engine."""
    path = ROOT / "data/tibetan_transcription_correction_authority.tsv"
    if not path.exists():
        return [], []
    ledger = read(path)
    fields = list(ledger[0]) if ledger else []
    for field in (
        "signature_condition_results", "current_prior_decision_record",
    ):
        if field not in fields:
            fields.append(field)
    by_operation: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in registry_rows:
        if record["authorization_status"].startswith("authorized"):
            by_operation[record["operation_signature"]].append(record)
    aligned = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in aligned_rows
    }
    echo = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in read(ROOT / "data/reviewed_final_ng_echo_decisions.tsv")
    }
    exceptions = {
        (r["tibetan_syllable"], r["source_token"]): r
        for r in read(
            ROOT / "data/reviewed_tibetan_transcription_exceptions.tsv"
        )
    }
    for row in ledger:
        key = tuple(row[field] for field in (
            "volume", "page", "line", "token_index"
        ))
        exact = dict(aligned.get(key, {}))
        exact.setdefault("tibetan_syllable", row["tibetan_syllable"])
        exact.setdefault("token_boundary_status", row["token_boundary_status"])
        exact["latin_token"] = row["observed_source"]
        operations = canonical.edit_operations(
            row["observed_source"], row["target"]
        )
        matches: list[str] = []
        results: list[str] = []
        all_covered = bool(operations)
        for operation in operations:
            operation_matches: list[str] = []
            operation_results: list[str] = []
            for record in by_operation.get(operation["signature"], []):
                applies, reason = signature_applies_to_row(
                    record, exact, row["target"]
                )
                operation_results.append(
                    f"{record['signature_id']}={reason}"
                )
                if applies:
                    operation_matches.append(record["signature_id"])
            if not operation_matches:
                all_covered = False
            matches.extend(operation_matches)
            results.extend(operation_results or [
                f"{operation['signature']}=no_current_A_child"
            ])
        controlling = ""
        echo_row = echo.get(key)
        if echo_row and echo_row["decision"] in {
            "deferred", "rejected", "resolved_elsewhere",
        }:
            controlling = (
                f"final_ng_echo:{echo_row['decision']}:"
                f"{echo_row.get('reviewing_batch', '')}"
            )
        exception = exceptions.get(
            (row["tibetan_syllable"], row["observed_source"])
        )
        if (
            not controlling and exception
            and exception.get("exception_scope") in {
                "canonical_target_block", "family_block", "alignment_block",
            }
        ):
            controlling = (
                f"transcription_exception:{exception['status']}:"
                f"{exception['exception_scope']}"
            )
        row["ocr_signature_ids"] = (
            ";".join(sorted(set(matches))) if matches
            else "exact_row_review_only"
        )
        row["signature_condition_results"] = ";".join(results)
        row["current_signature_authority"] = "yes" if all_covered else "no"
        row["current_structural_gate"] = "yes" if all_covered else "no"
        row["current_prior_decision_gate"] = "no" if controlling else "yes"
        row["current_prior_decision_record"] = controlling or "none"
        row["prior_exact_decision_status"] = controlling or "none"
        row["current_propagation_authority"] = "yes" if all((
            row["current_target_authority"] in {
                "canonical_reviewed", "canonical_independent_strong",
                "canonical_feature_composed",
            },
            all_covered,
            row["current_alignment_gate"] == "yes",
            row["current_boundary_gate"] == "yes",
            row["current_domain_gate"] == "yes",
            not controlling,
        )) else "no"
    return ledger, fields
BOUNDARY_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "captured_token", "token_start", "token_end", "preceding_character",
    "following_character", "boundary_status", "context_excerpt",
]
CONDITION_BACKTEST_FIELDS = [
    "signature", "condition_matching_reviewed_occurrences",
    "condition_failing_reviewed_occurrences", "reviewed_failure_reasons",
    "residual_signature_occurrences", "residual_condition_matches",
    "residual_condition_failures", "residual_failure_reasons",
]
HYPOTHETICAL_D_SCOPE_FIELDS = [
    "signature_id", "operation_signature", "current_exact_candidates",
    "condition_matches", "condition_failures", "distinct_syllables",
    "exact_alternate_target_agreements", "exact_alternate_source_agreements",
    "exact_alternate_conflicts", "failure_reasons", "matched_identities",
]

CANONICAL_TIBETAN_ROLES = {
    "", "prefix", "superscript", "root_consonant",
    "subjoined_consonants", "vowel", "suffix_coda", "post_suffix",
}
POSITION_TYPES = {
    "", "token_initial", "token_final", "exact_index",
    "within_target_role_span", "source_internal",
    "source_initial_or_internal", "extra_source_initial",
    "extra_source_final",
}
DOMAINS = {
    "ordinary_tibetan_lexical_or_compound", "tibetan_proper_name",
    "sanskrit_or_indic_transcription", "foreign_transcription",
    "bibliography_or_citation", "german_gloss_or_prose", "unclear",
}


def read(path: Path) -> list[dict[str, str]]:
    return integrity.read_tsv(path)


def write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    integrity.write_tsv(path, rows, fields)


def split_signature(signature: str) -> tuple[str, str, str]:
    if signature.startswith("SUB ") and "→" in signature:
        source, target = signature[4:].split("→", 1)
        return "substitution", source, target
    if signature.startswith("DEL "):
        return "deletion", signature[4:], ""
    if signature.startswith("INS "):
        return "insertion", "", signature[4:]
    return "complex", signature, ""


def attribute_edit_to_spans(
    source: str,
    target: str,
    operation: dict[str, str],
    spans: list[dict[str, str]],
    domain: str,
) -> dict[str, str]:
    """Locate one OCR edit against exact canonical role spans."""
    source_start = int(operation["source_position"])
    source_end = source_start + len(operation["source_span"])
    target_start = int(operation["target_position"])
    target_end = target_start + len(operation["target_span"])
    if not operation["target_span"]:
        if source_start == 0:
            source_location = "extra_source_material:token_initial"
        elif source_end == len(source):
            source_location = "extra_source_material:token_final"
        else:
            source_location = "extra_source_material:internal"
        matching: list[dict[str, str]] = []
        extra = "yes"
    else:
        matching = [
            span for span in spans
            if target_start < int(span["target_end"])
            and target_end > int(span["target_start"])
        ]
        source_location = (
            "canonical_corresponding_span:"
            + ",".join(span["tibetan_role"] for span in matching)
            if matching else "structural_location_unresolved"
        )
        extra = "no"
    roles = sorted({span["tibetan_role"] for span in matching})
    features = sorted({span["tibetan_feature"] for span in matching})
    rule_ids = sorted({span["rule_id"] for span in matching})
    return {
        "source_edit_start": str(source_start),
        "source_edit_end": str(source_end),
        "target_edit_start": str(target_start),
        "target_edit_end": str(target_end),
        "source_structural_location": source_location,
        "target_structural_role": ";".join(roles) or "none",
        "tibetan_role": ";".join(roles) or "none",
        "tibetan_feature": ";".join(features) or "none",
        "parent_structural_unit": (
            "role_span" if len(roles) == 1 else
            "between_or_multi_role" if roles else "extra_source_material"
        ),
        "target_component_rule_id": ";".join(rule_ids) or "none",
        "crosses_role_boundaries": "yes" if len(roles) > 1 else "no",
        "extra_source_material": extra,
        "edit_specific_domain_condition": domain or "unresolved",
        "attribution_status": (
            "structurally_attributed" if matching or extra == "yes"
            else "structurally_unresolved"
        ),
    }


def primitive_decomposition(
    source: str, target: str, operation_signature: str
) -> list[str]:
    """Decompose recognised compounds diagnostically, never authoritatively."""
    if (
        operation_signature == "REPLACE ni→ṅ"
        and source.endswith("ni") and target.endswith("ṅ")
        and source[:-2] == target[:-1]
    ):
        return ["SUB n→ṅ", "DEL token-final i after n"]
    return [operation_signature]


def applicable_operations(
    operations: list[dict[str, str]], scope: str
) -> list[dict[str, str]]:
    if scope == "feature_only_final_nasal":
        return [
            op for op in operations
            if op["target_span"] == "ṅ"
            and op["source_span"] in {"n", "h", "ñ", "ń", "ň"}
        ]
    if scope == "feature_only_root":
        return [
            op for op in operations
            if op["signature"] in {"SUB I→l", "SUB Z→ź", "SUB z→ź"}
        ]
    if scope in {
        "full_token_explicit_review", "full_token_independent_canonical"
    } and len(operations) == 1:
        return operations
    return []


def classify_learning(
    scope: str, teaching: str, operations: list[dict[str, str]],
    superseded: bool,
) -> str:
    if superseded:
        return "not_signature_learning_evidence"
    if scope in {"marker_only", "punctuation_only"}:
        return "structural_or_punctuation_edit"
    if scope.startswith("feature_only"):
        return "feature_specific_review"
    if (
        scope in {"full_token_explicit_review", "full_token_independent_canonical"}
        and teaching != "alternate_witness_only"
    ):
        return (
            "atomic_reviewed_edit" if len(operations) == 1
            else "reviewed_composed_edit"
        )
    if scope == "composed_repair":
        return "reviewed_composed_edit"
    return "not_signature_learning_evidence"


def reviewed_evidence() -> tuple[
    list[dict[str, str]], dict[str, list[dict[str, str]]], Counter[str]
]:
    scopes = {
        row["reason"]: row
        for row in read(ROOT / "data/reviewed_correction_evidence_scopes.tsv")
    }
    aligned = integrity.collect_all_aligned(ROOT / "release/current")
    aligned_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in aligned
    }
    supersessions = read(ROOT / "data/reviewed_correction_supersessions.tsv")
    superseded = {
        (
            r["volume"], r["page"], r["line"], r["token_index"],
            r["original_source"], r["old_target"],
        )
        for r in supersessions if r.get("status") == "active"
    }
    output: list[dict[str, str]] = []
    positive: dict[str, list[dict[str, str]]] = defaultdict(list)
    negatives: Counter[str] = Counter()
    for row in read(ROOT / "data/reviewed_tibetan_exact_overrides.tsv"):
        key = (row["volume"], row["page"], row["line"], row["token_index"])
        aligned_row = aligned_by_key.get(key, {})
        scope_row = scopes.get(row["reason"], {})
        scope = scope_row.get("evidence_scope", "other")
        teaching = scope_row.get(
            "canonical_teaching_status", "not_teaching_evidence"
        )
        operations = canonical.edit_operations(
            row["from_token"], row["to_token"]
        )
        is_superseded = (
            key + (row["from_token"], row["to_token"])
        ) in superseded
        learning = classify_learning(scope, teaching, operations, is_superseded)
        usable = applicable_operations(operations, scope)
        evidence_row = {
            "volume": row["volume"], "page": row["page"],
            "line": row["line"], "token_index": row["token_index"],
            "tibetan_syllable": aligned_row.get("tibetan_syllable", ""),
            "source": row["from_token"], "target": row["to_token"],
            "learning_class": learning, "evidence_scope": scope,
            "canonical_teaching_status": teaching,
            "operation_signatures": ";".join(
                op["signature"] for op in operations
            ),
            "operation_count": str(len(operations)),
            "domain": integrity.classify_domain(
                aligned_row.get("zone", ""),
                aligned_row.get("context_excerpt", ""),
            ),
            "reason": row["reason"], "evidence": row["evidence"],
            "review_note": row.get("review_note", ""),
            "history_status": "superseded" if is_superseded else "active",
        }
        output.append(evidence_row)
        for op in usable:
            positive[op["signature"]].append(evidence_row)
    for row in supersessions:
        old_operations = canonical.edit_operations(
            row["original_source"], row["old_target"]
        )
        output.append({
            "volume": row["volume"], "page": row["page"],
            "line": row["line"], "token_index": row["token_index"],
            "tibetan_syllable": row["tibetan_syllable"],
            "source": row["original_source"], "target": row["old_target"],
            "learning_class": "not_signature_learning_evidence",
            "evidence_scope": "superseded",
            "canonical_teaching_status": "superseded",
            "operation_signatures": ";".join(
                op["signature"] for op in old_operations
            ),
            "operation_count": str(len(old_operations)),
            "domain": "ordinary_tibetan_lexical_or_compound",
            "reason": row["supersession_reason"],
            "evidence": row["evidence"],
            "review_note": (
                f"Superseded historical target; effective target is "
                f"{row['superseding_target']}."
            ),
            "history_status": "superseded",
        })
        # The old edit is retained as negative/history evidence, but it is not
        # a contradiction of a component operation that remains valid (for
        # example n→ṅ inside an incomplete Zan→Zaṅ target).
        negatives["SUPERSEDED_INCOMPLETE_TARGET"] += 1
    return output, positive, negatives


def alternate_support() -> dict[str, Counter[str]]:
    result: dict[str, Counter[str]] = defaultdict(Counter)
    for path in sorted((ROOT / "release/current/qa").glob(
        "*/**/*alternate_witness_*.tsv"
    )):
        kind = "adopted" if "adoptions" in path.name else "unresolved"
        for row in read(path):
            source = row.get("base_token", "")
            target = row.get("alternate_token", "")
            if not source or not target:
                continue
            operations = canonical.edit_operations(source, target)
            for op in operations:
                result[op["signature"]][kind] += 1
    for path in sorted((ROOT / "release/current/qa").glob(
        "*/tibetan_cleanup_diagnostics/tibetan_google_candidate_readings.tsv"
    )):
        for row in read(path):
            source = row.get("base_token", "")
            target = row.get("alternate_token", "") or row.get(
                "proposed_target", ""
            )
            if not source or not target or source == target:
                continue
            for op in canonical.edit_operations(source, target):
                result[op["signature"]]["candidate"] += 1
    return result


def exact_alternate_support() -> dict[tuple[str, str, str, str, str], list[dict[str, str]]]:
    result: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for path in sorted((ROOT / "release/current/qa").glob(
        "*/**/*alternate_witness_*.tsv"
    )):
        volume = path.parts[-2]
        status = "adopted" if "adoptions" in path.name else "unresolved"
        for row in read(path):
            key = (
                volume, row.get("page", ""), row.get("line", ""),
                row.get("token_index", ""), row.get("base_token", ""),
            )
            result[key].append({
                "status": status,
                "token": row.get("alternate_token", ""),
            })
    for path in sorted((ROOT / "release/current/qa").glob(
        "*/tibetan_cleanup_diagnostics/tibetan_google_candidate_readings.tsv"
    )):
        for row in read(path):
            key = (
                row.get("volume", path.parts[-3]),
                row.get("page", ""), row.get("line", ""),
                row.get("token_index", ""), row.get("base_token", ""),
            )
            item = {
                "status": "candidate",
                "token": row.get("alternate_token", ""),
            }
            if item not in result[key]:
                result[key].append(item)
    return result


def decisions() -> dict[str, dict[str, str]]:
    path = ROOT / "data/reviewed_tibetan_ocr_signature_decisions.tsv"
    rows = read(path) if path.exists() else []
    for row in rows:
        validate_signature_condition(row)
    return {row["signature"]: row for row in rows}


def _split_values(value: str) -> set[str]:
    return {item for item in value.split(";") if item}


def validate_signature_condition(row: dict[str, str]) -> None:
    """Reject persisted conditions that the evaluator cannot execute."""
    role = row.get("tibetan_role", "")
    if role not in CANONICAL_TIBETAN_ROLES:
        raise ValueError(
            f"{row['signature']}: noncanonical Tibetan role {role!r}"
        )
    for field in ("source_position_type", "target_position_type"):
        value = row.get(field, "")
        if value not in POSITION_TYPES:
            raise ValueError(
                f"{row['signature']}: unknown {field} {value!r}"
            )
    for field in ("source_position_value", "target_position_value"):
        value = row.get(field, "")
        if value and not value.isdigit():
            raise ValueError(
                f"{row['signature']}: {field} must be an integer"
            )
    unknown_domains = _split_values(row.get("domain_condition", "")) - DOMAINS
    if unknown_domains:
        raise ValueError(
            f"{row['signature']}: unknown domain predicates "
            f"{sorted(unknown_domains)}"
        )
    forbidden_roles = _split_values(
        row.get("forbidden_tibetan_roles", "")
    )
    if forbidden_roles - CANONICAL_TIBETAN_ROLES:
        raise ValueError(
            f"{row['signature']}: unknown forbidden Tibetan roles "
            f"{sorted(forbidden_roles - CANONICAL_TIBETAN_ROLES)}"
        )
    for predicate in _split_values(
        row.get("forbidden_tibetan_role_features", "")
    ):
        if "=" not in predicate:
            raise ValueError(
                f"{row['signature']}: malformed forbidden role-feature "
                f"predicate {predicate!r}"
            )
        predicate_role, predicate_feature = predicate.split("=", 1)
        if predicate_role not in CANONICAL_TIBETAN_ROLES or not predicate_feature:
            raise ValueError(
                f"{row['signature']}: unknown forbidden role-feature "
                f"predicate {predicate!r}"
            )
    for field in (
        "canonical_target_required", "aligned_tibetan_required",
        "crosses_role_boundaries", "extra_source_material",
    ):
        value = row.get(field, "")
        if value not in {"", "yes", "no"}:
            raise ValueError(
                f"{row['signature']}: {field} must be yes/no/blank"
            )
    if (
        row.get("source_position_type") == "exact_index"
        and not row.get("source_position_value")
    ):
        raise ValueError(f"{row['signature']}: source exact index missing")
    if (
        row.get("target_position_type") == "exact_index"
        and not row.get("target_position_value")
    ):
        raise ValueError(f"{row['signature']}: target exact index missing")


_ROLE_SPANS_CACHE: dict[
    tuple[str, str], list[dict[str, str]]
] | None = None


def canonical_role_spans(
    tibetan_syllable: str, target: str,
) -> list[dict[str, str]]:
    global _ROLE_SPANS_CACHE
    if _ROLE_SPANS_CACHE is None:
        _ROLE_SPANS_CACHE = defaultdict(list)
        for span in read(
            ROOT / "data/tibetan_latin_canonical_role_spans.tsv"
        ):
            _ROLE_SPANS_CACHE[
                (span["tibetan_syllable"], span["target"])
            ].append(span)
    return _ROLE_SPANS_CACHE.get((tibetan_syllable, target), [])


def _position_matches(
    position_type: str, position_value: str,
    operation: dict[str, str], source: str, target: str, side: str,
    attribution: dict[str, str],
) -> bool:
    start = int(operation[f"{side}_position"])
    span = operation[f"{side}_span"]
    end = start + len(span)
    token = source if side == "source" else target
    if not position_type:
        return True
    if position_type == "token_initial":
        return start == 0
    if position_type == "token_final":
        return end == len(token)
    if position_type == "exact_index":
        return start == int(position_value)
    if position_type == "source_internal":
        return side == "source" and start > 0 and end < len(source)
    if position_type == "source_initial_or_internal":
        return side == "source" and end < len(source)
    if position_type == "extra_source_initial":
        return (
            side == "source"
            and attribution["source_structural_location"]
            == "extra_source_material:token_initial"
        )
    if position_type == "extra_source_final":
        return (
            side == "source"
            and attribution["source_structural_location"]
            == "extra_source_material:token_final"
        )
    if position_type == "within_target_role_span":
        return side == "target" and attribution["target_structural_role"] != "none"
    raise ValueError(f"unhandled position type {position_type!r}")


def reviewed_echo_identity_keys() -> set[tuple[str, str, str, str]]:
    path = ROOT / "data/reviewed_final_ng_echo_decisions.tsv"
    return {
        (row["volume"], row["page"], row["line"], row["token_index"])
        for row in read(path)
    } if path.exists() else set()


def signature_applies_to_row(
    signature_record: dict[str, str],
    row: dict[str, str],
    canonical_target: str,
) -> tuple[bool, str]:
    """Evaluate a persisted signature condition against one exact row."""
    if row.get("token_boundary_status") != "token_boundary_secure":
        return False, "insecure_token_boundary"
    validate_signature_condition(signature_record)
    if (
        signature_record.get("aligned_tibetan_required") == "yes"
        and not row.get("tibetan_syllable")
    ):
        return False, "aligned_tibetan_missing"
    identities = _split_values(
        signature_record.get("exact_tibetan_identities", "")
    )
    if identities and row.get("tibetan_syllable") not in identities:
        return False, "exact_tibetan_identity_mismatch"
    domain = integrity.classify_domain(
        row.get("zone", ""), row.get("context_excerpt", "")
    )
    required_domain = signature_record.get("domain_condition", "")
    allowed_domains = {
        item for item in required_domain.split(";") if item
    }
    if allowed_domains and domain not in allowed_domains:
        return False, "domain_mismatch"
    source = row.get("latin_token", "")
    source_pattern = signature_record.get("source_context_pattern", "")
    target_pattern = signature_record.get("target_context_pattern", "")
    if source_pattern and not re.search(source_pattern, source):
        return False, "source_context_mismatch"
    if target_pattern and not re.search(target_pattern, canonical_target):
        return False, "target_context_mismatch"
    operations = [
        op for op in canonical.edit_operations(source, canonical_target)
        if op["signature"] == signature_record.get("operation_signature")
    ]
    if not operations:
        return False, "signature_not_in_edit_script"
    role = signature_record.get("tibetan_role", "")
    feature = signature_record.get("tibetan_feature", "")
    forbidden_features = _split_values(
        signature_record.get("forbidden_tibetan_features", "")
    )
    if forbidden_features and any(
        item in row["tibetan_syllable"] for item in forbidden_features
    ):
        return False, "forbidden_tibetan_feature"
    forbidden_roles = _split_values(
        signature_record.get("forbidden_tibetan_roles", "")
    )
    spans = canonical_role_spans(
        row["tibetan_syllable"], canonical_target
    )
    # A local coda gate does not require segmentation of the entire target.
    # It is independently delimited by the resolved Tibetan coda, the
    # token-final edit, and the authoritative target's final glyph.
    local_final_ng = (
        role == "suffix_coda" and feature == "ང"
        and signature_record.get("target_position_type") == "token_final"
        and canonical_target.endswith("ṅ")
        and row.get("tibetan_syllable", "").endswith("ང")
    )
    span_roles = {span["tibetan_role"] for span in spans}
    if forbidden_roles & span_roles:
        return False, "forbidden_tibetan_role"
    forbidden_role_features = _split_values(
        signature_record.get("forbidden_tibetan_role_features", "")
    )
    present_role_features = {
        f"{span['tibetan_role']}={span['tibetan_feature']}" for span in spans
    }
    if forbidden_role_features & present_role_features:
        return False, "forbidden_tibetan_role_feature"
    if role and not local_final_ng and not any(
        span["tibetan_role"] == role
        and (not feature or span["tibetan_feature"] == feature)
        for span in spans
    ):
        return False, (
            "tibetan_role_mismatch" if feature else "tibetan_role_missing"
        )
    failure_reasons: list[str] = []
    for operation in operations:
        attribution = attribute_edit_to_spans(
            source, canonical_target, operation, spans, domain
        )
        if local_final_ng and int(operation["target_position"]) + len(
            operation["target_span"]
        ) == len(canonical_target):
            attribution = dict(attribution)
            attribution["target_structural_role"] = "suffix_coda"
            attribution["tibetan_role"] = "suffix_coda"
            attribution["tibetan_feature"] = "ང"
            attribution["parent_structural_unit"] = "suffix_coda:ང"
        if not _position_matches(
            signature_record.get("source_position_type", ""),
            signature_record.get("source_position_value", ""),
            operation, source, canonical_target, "source", attribution,
        ):
            failure_reasons.append("source_position_mismatch")
            continue
        if not _position_matches(
            signature_record.get("target_position_type", ""),
            signature_record.get("target_position_value", ""),
            operation, source, canonical_target, "target", attribution,
        ):
            failure_reasons.append("target_position_mismatch")
            continue
        for condition_field, observed_field in (
            ("source_structural_location", "source_structural_location"),
            ("target_structural_role", "target_structural_role"),
            ("parent_structural_unit", "parent_structural_unit"),
            ("crosses_role_boundaries", "crosses_role_boundaries"),
            ("extra_source_material", "extra_source_material"),
        ):
            required = signature_record.get(condition_field, "")
            if required and attribution[observed_field] != required:
                failure_reasons.append(f"{condition_field}_mismatch")
                break
        else:
            if (
                role and attribution["target_structural_role"] != role
                and not (
                    role == "suffix_coda"
                    and signature_record.get("target_position_type")
                    == "token_final"
                )
            ):
                failure_reasons.append("edit_role_span_mismatch")
                continue
            if (
                feature and attribution["tibetan_feature"] != feature
                and attribution["tibetan_feature"] != "none"
            ):
                failure_reasons.append("edit_feature_span_mismatch")
                continue
            if (
                signature_record.get("canonical_target_required") == "yes"
                and not canonical_target
            ):
                return False, "canonical_target_missing"
            return True, "condition_match"
    return False, failure_reasons[0] if failure_reasons else "condition_mismatch"


def build() -> dict[str, list[dict[str, str]]]:
    evidence, positives, negatives = reviewed_evidence()
    alternate = alternate_support()
    exact_alternates = exact_alternate_support()
    echo_identity_keys = reviewed_echo_identity_keys()
    outliers = read(ROOT / "data/tibetan_latin_transcription_outliers.tsv")
    canon_rows = read(ROOT / "data/tibetan_latin_canonical_syllables.tsv")
    canon_by_syllable = {r["tibetan_syllable"]: r for r in canon_rows}
    concordance = read(ROOT / "data/tibetan_latin_syllable_concordance.tsv")
    role_spans = read(ROOT / "data/tibetan_latin_canonical_role_spans.tsv")
    spans_by_target: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for span in role_spans:
        spans_by_target[(span["tibetan_syllable"], span["target"])].append(span)
    decision_map = decisions()
    transcription_exceptions = {
        (r["tibetan_syllable"], r["source_token"]): r
        for r in read(
            ROOT / "data/reviewed_tibetan_transcription_exceptions.tsv"
        )
    }
    edit_attributions: list[dict[str, str]] = []

    candidate_signatures = set(positives) | {
        signature
        for row in outliers for signature in row["edit_signatures"].split(";")
        if signature
    }
    control_rows: list[dict[str, str]] = []
    registry_rows: list[dict[str, str]] = []
    for signature in sorted(candidate_signatures):
        op_type, source, target = split_signature(signature)
        reviewed = positives.get(signature, [])
        syllables = sorted({
            row["tibetan_syllable"] for row in reviewed
            if row["tibetan_syllable"]
        })
        legitimate = [
            row for row in concordance
            if source and source in row["latin_form"]
            and row["latin_form"] in canon_by_syllable.get(
                row["tibetan_syllable"], {}
            ).get("canonical_forms", "").split(";")
        ]
        foreign = sum(
            int(row["current_clean_occurrences"])
            for row in legitimate
            if any(
                risky in row["domain_breakdown"]
                for risky in (
                    "sanskrit_or_indic_transcription",
                    "tibetan_proper_name", "unclear",
                )
            )
        )
        alt = alternate.get(signature, Counter())
        control_rows.append({
            "signature": signature,
            "reviewed_positive_syllables": str(len(syllables)),
            "reviewed_positive_occurrences": str(len(reviewed)),
            "historical_positive_occurrences": "0",
            "alternate_witness_adopted": str(alt["adopted"]),
            "alternate_witness_unresolved_or_candidate": str(
                alt["unresolved"] + alt["candidate"]
            ),
            "alternate_witness_conflicts": "0",
            "legitimate_source_form_controls": str(len(legitimate)),
            "ambiguous_cases": str(sum(
                1 for row in outliers
                if signature in row["edit_signatures"].split(";")
                and canon_by_syllable.get(
                    row["tibetan_syllable"], {}
                ).get("canonical_confidence_tier") == "ambiguous"
            )),
            "foreign_domain_cases": str(foreign),
            "alignment_noise_cases": "0",
            "superseded_negative_count": str(negatives[signature]),
            "control_examples": ";".join(
                f"{r['tibetan_syllable']}={r['latin_form']}"
                for r in legitimate[:8]
            ) or "none",
        })
        decision = decision_map.get(signature)
        if decision:
            status = {
                "A": (
                    "authorized_role_conditioned"
                    if any(decision.get(field, "") for field in (
                        "tibetan_role", "tibetan_feature",
                        "source_position_type", "target_position_type",
                        "source_structural_location",
                        "target_structural_role", "source_context_pattern",
                        "target_context_pattern", "domain_condition",
                    ))
                    else "authorized"
                ),
                "D": "candidate_review", "R": "rejected",
            }[decision["decision"]]
            rationale = decision["evidence_summary"]
            evidence_tier = "persistent_reviewed_decision"
        else:
            status = "diagnostic_only"
            if len(syllables) >= 2 and len(reviewed) >= 3:
                status = "candidate_review"
            rationale = (
                "No persistent authorization decision; frequency alone is "
                "diagnostic and cannot authorize correction."
            )
            evidence_tier = "reviewed_atomic_candidate" if reviewed else "empirical_only"
        registry_rows.append({
            "signature_id": (
                "sig_" + signature.replace(" ", "_").replace("→", "_to_")
            ),
            "operation_signature": signature,
            "operation_type": op_type, "source_sequence": source,
            "target_sequence": target,
            "parent_signature": decision.get("parent_signature", "")
            if decision else "",
            "tibetan_role": decision.get("tibetan_role", "")
            if decision else "",
            "tibetan_feature": decision.get("tibetan_feature", "")
            if decision else "",
            "source_position_type": decision.get(
                "source_position_type", ""
            ) if decision else "",
            "source_position_value": decision.get(
                "source_position_value", ""
            ) if decision else "",
            "target_position_type": decision.get(
                "target_position_type", ""
            ) if decision else "",
            "target_position_value": decision.get(
                "target_position_value", ""
            ) if decision else "",
            "source_context_pattern": decision.get(
                "source_context_pattern", ""
            ) if decision else "",
            "target_context_pattern": decision.get(
                "target_context_pattern", ""
            ) if decision else "",
            "domain_condition": decision.get(
                "domain_condition", ""
            ) if decision else "",
            **{
                field: decision.get(field, "") if decision else ""
                for field in (
                    "source_structural_location", "target_structural_role",
                    "parent_structural_unit", "crosses_role_boundaries",
                    "extra_source_material", "forbidden_tibetan_roles",
                    "forbidden_tibetan_features",
                    "forbidden_tibetan_role_features",
                    "exact_tibetan_identities",
                )
            },
            "canonical_target_required": decision.get(
                "canonical_target_required", "yes"
            ) if decision else "yes",
            "aligned_tibetan_required": decision.get(
                "aligned_tibetan_required", "yes"
            ) if decision else "yes",
            "reviewed_atomic_supporting_syllables": str(len(syllables)),
            "reviewed_supporting_occurrences": str(len(reviewed)),
            "reviewed_supporting_volumes": ";".join(sorted({
                row["volume"] for row in reviewed if row["volume"]
            })),
            "reviewed_page_ranges": ";".join(
                f"{volume}:{min(pages)}-{max(pages)}"
                for volume in sorted({
                    row["volume"] for row in reviewed if row["volume"]
                })
                if (pages := [
                    int(row["page"]) for row in reviewed
                    if row["volume"] == volume and row["page"].isdigit()
                ])
            ),
            "historical_support": "0",
            "alternate_witness_support": str(
                alt["adopted"] + alt["unresolved"] + alt["candidate"]
            ),
            "legitimate_controls": str(len(legitimate)),
            "conflicts": str(negatives[signature]),
            "evidence_tier": evidence_tier,
            "authorization_status": status, "rationale": rationale,
            "parent_operation_reviewed_support": str(len(reviewed)),
            "parent_operation_alternate_support": str(
                alt["adopted"] + alt["unresolved"] + alt["candidate"]
            ),
            "parent_operation_global_controls": str(len(legitimate)),
            "conditioned_reviewed_support": str(len(reviewed)),
            "conditioned_alternate_support": str(
                alt["adopted"] + alt["unresolved"] + alt["candidate"]
            ),
            "conditioned_controls": str(len(legitimate)),
            "conditioned_conflicts": str(negatives[signature]),
        })

    for decision in decision_map.values():
        parent = decision.get("parent_signature", "")
        if not parent:
            continue
        base = next((
            row for row in registry_rows
            if row["operation_signature"] == parent
        ), None)
        if not base:
            continue
        child = dict(base)
        child.update({
            "signature_id": decision["signature"],
            "parent_signature": parent,
            "tibetan_role": decision.get("tibetan_role", ""),
            "tibetan_feature": decision.get("tibetan_feature", ""),
            "source_position_type": decision.get(
                "source_position_type", ""
            ),
            "source_position_value": decision.get(
                "source_position_value", ""
            ),
            "target_position_type": decision.get(
                "target_position_type", ""
            ),
            "target_position_value": decision.get(
                "target_position_value", ""
            ),
            "source_context_pattern": decision.get(
                "source_context_pattern", ""
            ),
            "target_context_pattern": decision.get(
                "target_context_pattern", ""
            ),
            "domain_condition": decision.get("domain_condition", ""),
            **{
                field: decision.get(field, "")
                for field in (
                    "source_structural_location", "target_structural_role",
                    "parent_structural_unit", "crosses_role_boundaries",
                    "extra_source_material", "forbidden_tibetan_roles",
                    "forbidden_tibetan_features",
                    "forbidden_tibetan_role_features",
                    "exact_tibetan_identities",
                )
            },
            "canonical_target_required": decision.get(
                "canonical_target_required", "yes"
            ),
            "aligned_tibetan_required": decision.get(
                "aligned_tibetan_required", "yes"
            ),
            "evidence_tier": "persistent_reviewed_conditioned_child",
            "authorization_status": {
                "A": "authorized_role_conditioned",
                "D": "candidate_review", "R": "rejected",
            }[decision["decision"]],
            "rationale": decision["evidence_summary"],
            # Conditioned children never inherit authority evidence from the
            # primitive parent. Exact evidence is reattributed below.
            "reviewed_atomic_supporting_syllables": "0",
            "reviewed_supporting_occurrences": "0",
            "reviewed_supporting_volumes": "",
            "reviewed_page_ranges": "",
            "historical_support": "0",
            "alternate_witness_support": "0",
            "legitimate_controls": "0",
            "conflicts": "0",
            "conditioned_reviewed_support": "0",
            "conditioned_alternate_support": "0",
            "conditioned_controls": "0",
            "conditioned_conflicts": "0",
        })
        registry_rows.append(child)

    registry_by_signature: dict[str, list[dict[str, str]]] = defaultdict(list)
    for registry_row in registry_rows:
        registry_by_signature[
            registry_row["operation_signature"]
        ].append(registry_row)
    aligned_rows = integrity.collect_all_aligned(ROOT / "release/current")
    aligned_by_identity = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in aligned_rows
    }
    structural_alternates: list[dict[str, str]] = []
    conditioned_reviewed: dict[str, list[dict[str, str]]] = defaultdict(list)
    conditioned_alternate: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in registry_rows:
        if not record["parent_signature"]:
            continue
        for reviewed_row in positives.get(record["operation_signature"], []):
            exact = aligned_by_identity.get((
                reviewed_row["volume"], reviewed_row["page"],
                reviewed_row["line"], reviewed_row["token_index"],
            ))
            if not exact:
                continue
            historical = dict(exact)
            historical["latin_token"] = reviewed_row["source"]
            applies, _ = signature_applies_to_row(
                record, historical, reviewed_row["target"]
            )
            if applies:
                conditioned_reviewed[record["signature_id"]].append(
                    reviewed_row
                )
        for (volume, page, line, token_index, base), witnesses in (
            exact_alternates.items()
        ):
            exact = aligned_by_identity.get((volume, page, line, token_index))
            if not exact:
                continue
            historical = dict(exact)
            historical["latin_token"] = base
            canonical_row = canon_by_syllable.get(
                exact["tibetan_syllable"], {}
            )
            canonical_target = canonical_row.get("canonical_forms", "")
            for witness in witnesses:
                alternate_token = witness["token"]
                operations = canonical.edit_operations(base, alternate_token)
                relevant = [
                    op for op in operations
                    if op["signature"] == record["operation_signature"]
                ]
                if not relevant:
                    continue
                applies, reason = signature_applies_to_row(
                    record, historical, canonical_target
                )
                target_spans = spans_by_target.get(
                    (exact["tibetan_syllable"], canonical_target), []
                )
                attribution = attribute_edit_to_spans(
                    base, canonical_target, relevant[0], target_spans,
                    integrity.classify_domain(
                        exact.get("zone", ""), exact.get("context_excerpt", "")
                    ),
                )
                relation = (
                    "equals_canonical_target"
                    if alternate_token == canonical_target
                    else "equals_source" if alternate_token == base
                    else "differs_from_source_and_target"
                )
                structural_alternates.append({
                    "volume": volume, "page": page, "line": line,
                    "token_index": token_index,
                    "tibetan_syllable": exact["tibetan_syllable"],
                    "source": base, "alternate_token": alternate_token,
                    "canonical_target": canonical_target,
                    "target_authority": canonical_row.get(
                        "canonical_confidence_tier", ""
                    ),
                    "operation_signature": record["operation_signature"],
                    "signature_child_id": record["signature_id"],
                    "witness_type": witness["status"],
                    "alternate_relation": relation,
                    "condition_result": reason,
                    "unrelated_edits": str(max(0, len(operations) - 1)),
                    **{
                        field: attribution[field] for field in (
                            "source_structural_location",
                            "target_structural_role", "tibetan_role",
                            "tibetan_feature", "parent_structural_unit",
                        )
                    },
                })
                if applies and relation == "equals_canonical_target":
                    conditioned_alternate[record["signature_id"]].append(
                        structural_alternates[-1]
                    )
    for record in registry_rows:
        if not record["parent_signature"]:
            continue
        reviewed_rows = conditioned_reviewed[record["signature_id"]]
        alternate_rows = conditioned_alternate[record["signature_id"]]
        record["conditioned_reviewed_support"] = str(len(reviewed_rows))
        record["conditioned_alternate_support"] = str(len(alternate_rows))
        record["reviewed_supporting_occurrences"] = str(len(reviewed_rows))
        record["reviewed_atomic_supporting_syllables"] = str(len({
            row["tibetan_syllable"] for row in reviewed_rows
        }))
        record["reviewed_supporting_volumes"] = ";".join(sorted({
            row["volume"] for row in reviewed_rows
        }))
        record["alternate_witness_support"] = str(len(alternate_rows))
    correction_authority, correction_authority_fields = (
        reconcile_correction_authority(registry_rows, aligned_rows)
    )
    aligned_by_family: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for aligned_row in aligned_rows:
        aligned_by_family[(
            aligned_row["tibetan_syllable"], aligned_row["latin_token"]
        )].append(aligned_row)
    queue: list[dict[str, str]] = []
    for row in outliers:
        signatures = [s for s in row["edit_signatures"].split(";") if s]
        statuses = []
        for signature in signatures:
            records = registry_by_signature.get(signature, [])
            if any(
                record["authorization_status"].startswith("authorized")
                for record in records
            ):
                statuses.append("authorized_role_conditioned")
            elif any(
                record["authorization_status"] == "candidate_review"
                for record in records
            ):
                statuses.append("candidate_review")
            else:
                statuses.append("diagnostic_only")
        safe_domain = (
            row["domain_breakdown"]
            and all(
                part.startswith("ordinary_tibetan_lexical_or_compound:")
                for part in row["domain_breakdown"].split(";")
            )
        )
        exception = transcription_exceptions.get(
            (row["tibetan_syllable"], row["current_source"]), {}
        )
        if exception.get("status") == "foreign_or_alternate_transcription":
            safe_domain = False
        clean = row["damage_or_marker"] == "damage:0;marker:0"
        authorized = {
            "authorized", "authorized_role_conditioned",
            "authorized_domain_conditioned",
        }
        exact_rows = aligned_by_family.get(
            (row["tibetan_syllable"], row["current_source"]), []
        )
        operations = canonical.edit_operations(
            row["current_source"], row["canonical_forms"]
        )
        target_spans = spans_by_target.get(
            (row["tibetan_syllable"], row["canonical_forms"]), []
        )
        for exact in exact_rows:
            exact_domain = integrity.classify_domain(
                exact.get("zone", ""), exact.get("context_excerpt", "")
            )
            for operation in operations:
                edit_attributions.append({
                    "volume": exact["volume"], "page": exact["page"],
                    "line": exact["line"],
                    "token_index": exact["token_index"],
                    "tibetan_syllable": row["tibetan_syllable"],
                    "source": row["current_source"],
                    "canonical_target": row["canonical_forms"],
                    "source_alignment_status":
                        row["source_alignment_status"],
                    "boundary_status": exact["token_boundary_status"],
                    "domain": exact_domain,
                    "damage_or_marker": row["damage_or_marker"],
                    "operation_signature": operation["signature"],
                    **attribute_edit_to_spans(
                        row["current_source"], row["canonical_forms"],
                        operation, target_spans, exact_domain,
                    ),
                })
        boundary_secure = [
            exact for exact in exact_rows
            if exact["token_boundary_status"] == "token_boundary_secure"
        ]
        matching_rows = []
        failing_rows = []
        reviewed_echo_rows = []
        for exact in boundary_secure:
            identity = (
                exact["volume"], exact["page"], exact["line"],
                exact["token_index"],
            )
            if identity in echo_identity_keys:
                reviewed_echo_rows.append(exact)
                continue
            failures = []
            for signature, status in zip(signatures, statuses):
                if status not in authorized:
                    failures.append("signature_not_authorized")
                    continue
                applicable_records = [
                    record for record in registry_by_signature[signature]
                    if record["authorization_status"].startswith("authorized")
                ]
                results = [
                    signature_applies_to_row(
                        record, exact, row["canonical_forms"]
                    )
                    for record in applicable_records
                ]
                if not any(applies for applies, _reason in results):
                    failures.append(
                        results[0][1] if results else
                        "signature_not_authorized"
                    )
            (failing_rows if failures else matching_rows).append(exact)
        if reviewed_echo_rows and not matching_rows:
            action = "historical_echo_decision_block"
        elif row.get("source_alignment_status") == "gloss_alignment_noise":
            action = "gloss_alignment_noise"
        elif row.get("source_alignment_status") != "secure_transcription_outlier":
            action = "alignment_or_damage"
        elif not safe_domain:
            action = "domain_risk"
        elif not clean:
            action = "alignment_or_damage"
        elif (
            signatures and all(status in authorized for status in statuses)
            and matching_rows
        ):
            action = "ready_all_edits_authorized"
        elif signatures and all(status in authorized for status in statuses):
            action = "alignment_or_damage"
        elif sum(status not in authorized for status in statuses) == 1:
            action = "one_signature_missing"
        elif signatures:
            action = "multiple_signatures_missing"
        else:
            action = "complex_unexplained"
        target_ready = row["canonical_confidence_tier"] in {
            "canonical_reviewed", "canonical_independent_strong",
            "canonical_feature_composed",
        }
        signature_ready = bool(signatures) and all(
            status in authorized for status in statuses
        )
        alignment_ready = (
            row.get("source_alignment_status")
            == "secure_transcription_outlier"
        )
        boundary_ready = bool(boundary_secure)
        prior_ready = not reviewed_echo_rows
        final_ready = all((
            target_ready, signature_ready, alignment_ready, boundary_ready,
            safe_domain, clean, prior_ready, bool(matching_rows),
        ))
        queue.append({
            "tibetan_syllable": row["tibetan_syllable"],
            "current_source": row["current_source"],
            "canonical_target": row["canonical_forms"],
            "canonical_confidence_tier": row["canonical_confidence_tier"],
            "occurrence_count": row["occurrence_count"],
            "edit_signatures": row["edit_signatures"],
            "signature_statuses": ";".join(statuses),
            "action_category": action,
            "source_alignment_status": row.get(
                "source_alignment_status", "unresolved"
            ),
            "domain_breakdown": row["domain_breakdown"],
            "damage_or_marker": row["damage_or_marker"],
            "boundary_secure_occurrences": str(len(boundary_secure)),
            "condition_matching_occurrences": str(len(matching_rows)),
            "condition_failing_occurrences": str(len(failing_rows)),
            "canonical_evidence": row["canonical_evidence"],
            "target_authority_ready": "yes" if target_ready else "no",
            "ocr_signature_ready": "yes" if signature_ready else "no",
            "alignment_ready": "yes" if alignment_ready else "no",
            "boundary_ready": "yes" if boundary_ready else "no",
            "domain_ready": "yes" if safe_domain else "no",
            "prior_decision_ready": "yes" if prior_ready else "no",
            "final_action_ready": "yes" if final_ready else "no",
            "sample_contexts": row["sample_contexts"],
        })

    authorized_signatures = {
        sig for sig, records in registry_by_signature.items()
        if any(
            row["authorization_status"].startswith("authorized")
            for row in records
        )
    }
    exhaustion: list[dict[str, str]] = []
    for signature in sorted(authorized_signatures):
        matching = [
            row for row in queue
            if signature in row["edit_signatures"].split(";")
        ]
        ready = [
            row for row in matching
            if row["action_category"] == "ready_all_edits_authorized"
        ]
        exhaustion.append({
            "signature": signature,
            "remaining_outlier_families": str(len(matching)),
            "remaining_outlier_rows": str(sum(
                int(r["occurrence_count"]) for r in matching
            )),
            "authoritative_target_rows": str(sum(
                int(r["occurrence_count"]) for r in matching
            )),
            "clean_domain_safe_rows": str(sum(
                int(r["occurrence_count"]) for r in matching
                if r["action_category"] not in {
                    "domain_risk", "alignment_or_damage"
                }
            )),
            "ready_uncorrected_rows": str(sum(
                int(r["occurrence_count"]) for r in ready
            )),
            "disposition": (
                "bug_ready_rows_remain" if ready else
                "authorized_signature_clean_outliers_exhausted"
            ),
            "examples": ";".join(
                f"{r['tibetan_syllable']}:{r['current_source']}→{r['canonical_target']}"
                for r in matching[:6]
            ) or "none",
        })

    backaudit = read(ROOT / "data/final_ng_transcription_integrity_backaudit.tsv")
    incomplete_groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in backaudit:
        if row.get("proposed_disposition") in {
            "no_known_violation_but_incomplete", "unresolved"
        } or row.get("target_integrity_status") == "unresolved":
            incomplete_groups[(row["tibetan_syllable"], row["applied_target"])].append(row)
    incomplete: list[dict[str, str]] = []
    for (syllable, target), rows in sorted(incomplete_groups.items()):
        canon = canon_by_syllable.get(syllable, {})
        tier = canon.get("canonical_confidence_tier", "unresolved")
        incomplete.append({
            "tibetan_syllable": syllable, "active_target": target,
            "applied_target_count": str(len(rows)),
            "canonical_confidence_tier": tier,
            "historical_occurrences": canon.get("historical_occurrences", "0"),
            "independent_teaching_occurrences": canon.get(
                "independent_teaching_occurrences", "0"
            ),
            "competing_forms": canon.get("competing_forms", ""),
            "promotion_disposition": (
                "canonical_now_authoritative"
                if tier in {
                    "canonical_reviewed", "canonical_independent_strong",
                    "canonical_feature_composed",
                }
                and target in canon.get("canonical_forms", "").split(";")
                else "retain_incomplete"
            ),
        })

    moderate: list[dict[str, str]] = []
    for row in canon_rows:
        if row["canonical_confidence_tier"] != "canonical_independent_moderate":
            continue
        independent = int(row["independent_teaching_occurrences"])
        volumes = len([v for v in row["supporting_volumes"].split(";") if v])
        missing = []
        if independent < 3:
            missing.append("fewer_than_3_independent_occurrences")
        if volumes < 2:
            missing.append("single_volume")
        if row["competing_forms"]:
            missing.append("credible_competing_form")
        moderate.append({
            "tibetan_syllable": row["tibetan_syllable"],
            "candidate_forms": row["canonical_forms"],
            "independent_occurrences": str(independent),
            "volumes": row["supporting_volumes"],
            "entry_clusters": "",
            "historical_occurrences": row["historical_occurrences"],
            "competing_forms": row["competing_forms"],
            "missing_evidence": ";".join(missing) or "entry_cluster_independence",
            "promotion_disposition": "retain_moderate",
        })

    yields: Counter[str] = Counter()
    syllable_yields: dict[str, set[str]] = defaultdict(set)
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in queue:
        if row["action_category"] != "one_signature_missing":
            continue
        signatures = row["edit_signatures"].split(";")
        statuses = row["signature_statuses"].split(";")
        missing = next(
            (sig for sig, status in zip(signatures, statuses)
             if not status.startswith("authorized")), ""
        )
        if not missing:
            continue
        yields[missing] += int(row["occurrence_count"])
        syllable_yields[missing].add(row["tibetan_syllable"])
        examples[missing].append(row)
    packet: list[dict[str, str]] = []
    for signature, expected in yields.most_common(10):
        reg = next(iter(registry_by_signature.get(signature, [])), {})
        control = next(
            (r for r in control_rows if r["signature"] == signature), {}
        )
        conditioned_records = [
            record for record in registry_by_signature.get(signature, [])
            if record["signature_id"] != f"sig_{signature.replace(' ', '_').replace('→', '_to_')}"
            and decision_map.get(record["signature_id"], {}).get("decision")
            in {"A", "D", "R"}
        ]
        gated_collisions = 0
        same_tibetan_controls = 0
        gated_domain_controls = 0
        for family in examples[signature]:
            canonical_row = canon_by_syllable.get(
                family["tibetan_syllable"], {}
            )
            credible = set(filter(None, canonical_row.get(
                "credible_competing_transcriptions", ""
            ).split(";")))
            for exact in aligned_by_family.get(
                (family["tibetan_syllable"], family["current_source"]), []
            ):
                results = [
                    signature_applies_to_row(
                        record, exact, family["canonical_target"]
                    )
                    for record in conditioned_records
                ]
                if any(match for match, _reason in results):
                    if family["current_source"] in credible:
                        same_tibetan_controls += 1
                        gated_collisions += 1
                elif any(reason == "domain_mismatch" for _match, reason in results):
                    gated_domain_controls += 1
        emitted = 0
        for row in examples[signature]:
            exact_examples = aligned_by_family.get(
                (row["tibetan_syllable"], row["current_source"]), []
            ) or [{}]
            operations = canonical.edit_operations(
                row["current_source"], row["canonical_target"]
            )
            operation = next(
                (op for op in operations if op["signature"] == signature),
                operations[0] if operations else {
                    "signature": signature, "source_span": "",
                    "target_span": "", "source_position": "0",
                    "target_position": "0",
                },
            )
            attribution = attribute_edit_to_spans(
                row["current_source"], row["canonical_target"], operation,
                spans_by_target.get(
                    (row["tibetan_syllable"], row["canonical_target"]), []
                ),
                row["domain_breakdown"],
            )
            for exact in exact_examples:
                if emitted >= 20:
                    break
                packet.append({
                "signature": signature, "expected_clean_yield": str(expected),
                "expected_syllable_yield": str(len(syllable_yields[signature])),
                "reviewed_support": reg.get(
                    "reviewed_supporting_occurrences", "0"
                ),
                "alternate_witness_support": reg.get(
                    "alternate_witness_support", "0"
                ),
                "global_source_controls": control.get(
                    "legitimate_source_form_controls", "0"
                ),
                "gated_collision_controls": str(gated_collisions),
                "same_tibetan_competing_controls": str(
                    same_tibetan_controls
                ),
                "domain_controls": str(gated_domain_controls),
                "tibetan_syllable": row["tibetan_syllable"],
                "source": row["current_source"],
                "canonical_target": row["canonical_target"],
                "target_evidence": row["canonical_evidence"],
                "volume": exact.get("volume", ""),
                "page": exact.get("page", ""), "line": exact.get("line", ""),
                "token_index": exact.get("token_index", ""),
                "full_captured_source": exact.get(
                    "latin_token", row["current_source"]
                ),
                "preceding_character": exact.get("preceding_character", ""),
                "following_character": exact.get("following_character", ""),
                "boundary_status": exact.get(
                    "token_boundary_status", "unresolved"
                ),
                "operation_positions": ";".join(
                    f"{op['signature']}@{op['source_position']}"
                    for op in operations
                ),
                **{field: attribution[field] for field in (
                    "source_edit_start", "source_edit_end",
                    "target_edit_start", "target_edit_end",
                    "source_structural_location", "target_structural_role",
                    "tibetan_role", "tibetan_feature",
                    "parent_structural_unit", "target_component_rule_id",
                    "crosses_role_boundaries", "extra_source_material",
                    "edit_specific_domain_condition",
                )},
                "proposed_structural_role":
                    attribution["source_structural_location"],
                "primitive_edit_sequence": ";".join(
                    primitive_decomposition(
                        row["current_source"], row["canonical_target"],
                        signature,
                    )
                ),
                "authorized_components": (
                    "SUB n→ṅ" if signature == "REPLACE ni→ṅ" else "none"
                ),
                "missing_components": (
                    "DEL token-final i after n"
                    if signature == "REPLACE ni→ṅ" else "none"
                ),
                "compound_classification": (
                    "atomic_ocr_segmentation_signature_and_diagnostic_composition"
                    if signature == "REPLACE ni→ṅ"
                    else "single_edit_or_unclassified"
                ),
                "exact_alternate_witness_status": ";".join(
                    witness["status"] for witness in exact_alternates.get((
                        exact.get("volume", ""), exact.get("page", ""),
                        exact.get("line", ""), exact.get("token_index", ""),
                        exact.get("latin_token", row["current_source"]),
                    ), [])
                    if witness["token"] == row["canonical_target"]
                ) or "none",
                "exact_alternate_witness_token": ";".join(
                    witness["token"] for witness in exact_alternates.get((
                        exact.get("volume", ""), exact.get("page", ""),
                        exact.get("line", ""), exact.get("token_index", ""),
                        exact.get("latin_token", row["current_source"]),
                    ), [])
                ) or "none",
                "domain": row["domain_breakdown"],
                "context": exact.get(
                    "context_excerpt", row["sample_contexts"]
                ),
                "suggested_decision": "manual_signature_review",
                })
                emitted += 1
            if emitted >= 20:
                break
    boundary_audit = [
        {
            "volume": row["volume"], "page": row["page"],
            "line": row["line"], "token_index": row["token_index"],
            "tibetan_syllable": row["tibetan_syllable"],
            "captured_token": row["latin_token"],
            "token_start": row["token_start"], "token_end": row["token_end"],
            "preceding_character": row["preceding_character"] or "none",
            "following_character": row["following_character"] or "none",
            "boundary_status": row["token_boundary_status"],
            "context_excerpt": row["context_excerpt"],
        }
        for row in aligned_rows
        if row["token_boundary_status"] != "token_boundary_secure"
    ]
    aligned_by_identity = {
        (row["volume"], row["page"], row["line"], row["token_index"]): row
        for row in aligned_rows
    }
    condition_backtest: list[dict[str, str]] = []
    for signature in sorted(authorized_signatures):
        records = [
            record for record in registry_by_signature[signature]
            if record["authorization_status"].startswith("authorized")
        ]
        reviewed_matches = reviewed_failures = 0
        reviewed_reasons: Counter[str] = Counter()
        for evidence_row in evidence:
            if signature not in evidence_row["operation_signatures"].split(";"):
                continue
            exact = aligned_by_identity.get((
                evidence_row["volume"], evidence_row["page"],
                evidence_row["line"], evidence_row["token_index"],
            ))
            if not exact:
                reviewed_failures += 1
                reviewed_reasons["identity_not_resolved"] += 1
                continue
            exact = dict(exact)
            exact["latin_token"] = evidence_row["source"]
            results = [
                signature_applies_to_row(
                    record, exact, evidence_row["target"]
                ) for record in records
            ]
            if any(match for match, _reason in results):
                reviewed_matches += 1
            else:
                reviewed_failures += 1
                reviewed_reasons[
                    results[0][1] if results else "no_authorized_record"
                ] += 1
        residual = [
            row for row in queue
            if signature in row["edit_signatures"].split(";")
        ]
        residual_matches = sum(
            int(row["condition_matching_occurrences"]) for row in residual
        )
        residual_failures = sum(
            int(row["condition_failing_occurrences"]) for row in residual
        )
        condition_backtest.append({
            "signature": signature,
            "condition_matching_reviewed_occurrences": str(reviewed_matches),
            "condition_failing_reviewed_occurrences": str(reviewed_failures),
            "reviewed_failure_reasons": ";".join(
                f"{key}:{value}" for key, value in sorted(
                    reviewed_reasons.items()
                )
            ) or "none",
            "residual_signature_occurrences": str(sum(
                int(row["occurrence_count"]) for row in residual
            )),
            "residual_condition_matches": str(residual_matches),
            "residual_condition_failures": str(residual_failures),
            "residual_failure_reasons": (
                "condition_or_boundary_mismatch"
                if residual_failures else "none"
            ),
        })
    alignment_rescue: list[dict[str, str]] = []
    alignment_rescue_exact: list[dict[str, str]] = []
    family_alignment = {
        (item["tibetan_syllable"], item["current_source"]):
            item["source_alignment_status"]
        for item in outliers
    }

    def layout_signature(item: dict[str, str]) -> str:
        return "|".join((
            item.get("zone", "unresolved"),
            item.get("headword_transliteration_span_status", "unresolved"),
            f"token_index={item.get('token_index', '')}",
            f"preceding={'space' if item.get('preceding_character') == ' ' else 'other'}",
            f"following={'space' if item.get('following_character') == ' ' else 'other'}",
        ))

    layout_positive: Counter[str] = Counter()
    layout_negative: Counter[str] = Counter()
    for exact in aligned_rows:
        status = family_alignment.get(
            (exact["tibetan_syllable"], exact["latin_token"]), ""
        )
        signature = layout_signature(exact)
        if status == "secure_transcription_outlier":
            layout_positive[signature] += 1
        elif status in {"gloss_alignment_noise", "structurally_unaligned"}:
            layout_negative[signature] += 1
    for row in queue:
        if row["action_category"] != "alignment_or_damage":
            continue
        alignment = row["source_alignment_status"]
        damage = row["damage_or_marker"]
        if alignment == "probable_transcription_outlier":
            category = "probable_headword_span"
        elif alignment == "structurally_unaligned":
            category = "structurally_unaligned"
        elif alignment == "gloss_alignment_noise":
            category = "gloss_intrusion"
        elif "marker:" in damage and not damage.endswith("marker:0"):
            category = "marker_attached"
        elif "damage:" in damage and not damage.startswith("damage:0"):
            category = "damaged_ocr"
        elif row["boundary_ready"] == "no":
            category = "boundary_uncertainty"
        else:
            category = "other"
        alignment_rescue.append({
            "tibetan_syllable": row["tibetan_syllable"],
            "source": row["current_source"],
            "canonical_target": row["canonical_target"],
            "occurrence_count": row["occurrence_count"],
            "current_alignment_status": alignment,
            "rescue_category": category,
            "layout_evidence": "not_yet_independently_secure",
            "canonical_agreement_diagnostic_only": "yes",
            "upgrade_authorized": "no",
            "blocker":
                "layout_evidence_required_independent_of_desired_correction",
            "sample_contexts": row["sample_contexts"],
        })
        for exact in aligned_by_family.get(
            (row["tibetan_syllable"], row["current_source"]), []
        ):
            signature = layout_signature(exact)
            clean_exact = (
                exact["token_boundary_status"] == "token_boundary_secure"
                and exact["damage_scope"] in {
                    "none", "later_gloss_or_commentary",
                }
                and exact["marker_attached"] == "no"
            )
            high_precision_layout_candidate = (
                category == "probable_headword_span"
                and clean_exact and layout_positive[signature] >= 3
                and layout_negative[signature] == 0
                and exact["zone"] == "headword_line"
                and exact["headword_transliteration_span_status"]
                == "probable_span"
            )
            alignment_rescue_exact.append({
                "volume": exact["volume"], "page": exact["page"],
                "line": exact["line"],
                "token_index": exact["token_index"],
                "tibetan_syllable": exact["tibetan_syllable"],
                "source": exact["latin_token"],
                "canonical_target": row["canonical_target"],
                "current_alignment_status": alignment,
                "rescue_category": category,
                "line_zone": exact["zone"],
                "tibetan_token_ordinal": "unavailable",
                "latin_token_ordinal": exact["token_index"],
                "token_start": exact["token_start"],
                "token_end": exact["token_end"],
                "boundary_status": exact["token_boundary_status"],
                "damage_scope": exact["damage_scope"],
                "marker_attached": exact["marker_attached"],
                "layout_signature": signature,
                "positive_layout_support": str(layout_positive[signature]),
                "negative_layout_collisions": str(layout_negative[signature]),
                "upgrade_authorized": "no",
                "blocker": (
                    "candidate_zero_collision_layout_needs_exact_review"
                    if high_precision_layout_candidate else
                    "layout_pattern_not_zero_collision_high_support"
                ),
                "context_excerpt": exact["context_excerpt"],
            })
    hypothetical_d_scope: list[dict[str, str]] = []
    for decision in sorted(
        (item for item in decision_map.values() if item["decision"] == "D"),
        key=lambda item: item["signature"],
    ):
        operation_signature = (
            decision.get("parent_signature") or decision["signature"]
        )
        record = next((
            item for item in registry_rows
            if item["signature_id"] == decision["signature"]
            or (
                not decision.get("parent_signature")
                and item["operation_signature"] == decision["signature"]
            )
        ), None)
        if record is None:
            continue
        candidates: list[tuple[dict[str, str], str]] = []
        for family in outliers:
            if operation_signature not in family["edit_signatures"].split(";"):
                continue
            target = family["canonical_forms"]
            for exact in aligned_by_family.get(
                (family["tibetan_syllable"], family["current_source"]), []
            ):
                exact_with_gates = dict(exact)
                exact_with_gates["_source_alignment_status"] = (
                    family["source_alignment_status"]
                )
                exact_with_gates["_damage_or_marker"] = (
                    family["damage_or_marker"]
                )
                candidates.append((exact_with_gates, target))
        matches: list[tuple[dict[str, str], str]] = []
        failures: Counter[str] = Counter()
        alternate_counts: Counter[str] = Counter()
        for exact, target in candidates:
            if (
                exact["volume"], exact["page"], exact["line"],
                exact["token_index"],
            ) in echo_identity_keys:
                failures["controlling_exact_decision"] += 1
                continue
            if (
                exact["_source_alignment_status"]
                != "secure_transcription_outlier"
            ):
                failures["alignment_not_secure"] += 1
                continue
            if exact["_damage_or_marker"] != "damage:0;marker:0":
                failures["damage_or_marker"] += 1
                continue
            applies, reason = signature_applies_to_row(record, exact, target)
            if not applies:
                failures[reason] += 1
                continue
            unexplained = False
            for operation in canonical.edit_operations(
                exact["latin_token"], target
            ):
                if operation["signature"] == operation_signature:
                    continue
                other_records = [
                    item for item in registry_rows
                    if item["operation_signature"] == operation["signature"]
                    and item["authorization_status"].startswith("authorized")
                ]
                if not any(
                    signature_applies_to_row(
                        item, exact, target
                    )[0] for item in other_records
                ):
                    unexplained = True
                    break
            if unexplained:
                failures["other_unexplained_edit"] += 1
                continue
            matches.append((exact, target))
            alternate_rows = exact_alternates.get((
                exact["volume"], exact["page"], exact["line"],
                exact["token_index"], exact["latin_token"],
            ), [])
            for alternate_row in alternate_rows:
                token = alternate_row["token"]
                alternate_counts[
                    "target" if token == target else
                    "source" if token == exact["latin_token"] else "conflict"
                ] += 1
        hypothetical_d_scope.append({
            "signature_id": decision["signature"],
            "operation_signature": operation_signature,
            "current_exact_candidates": str(len(candidates)),
            "condition_matches": str(len(matches)),
            "condition_failures": str(len(candidates) - len(matches)),
            "distinct_syllables": str(len({
                item["tibetan_syllable"] for item, _target in matches
            })),
            "exact_alternate_target_agreements": str(
                alternate_counts["target"]
            ),
            "exact_alternate_source_agreements": str(
                alternate_counts["source"]
            ),
            "exact_alternate_conflicts": str(alternate_counts["conflict"]),
            "failure_reasons": ";".join(
                f"{key}:{value}" for key, value in sorted(failures.items())
            ) or "none",
            "matched_identities": ";".join(
                f"{item['volume']}:{item['page']}:{item['line']}:"
                f"{item['token_index']}:{item['tibetan_syllable']}:"
                f"{item['latin_token']}→{target}"
                for item, target in matches[:40]
            ) or "none",
        })
    active_queue_summary: list[dict[str, str]] = []
    for category in sorted({item["action_category"] for item in queue}):
        families = [
            item for item in queue if item["action_category"] == category
        ]
        current = [
            item for item in families if int(item["occurrence_count"]) > 0
        ]
        active_queue_summary.append({
            "queue_category": category,
            "family_count": str(len(families)),
            "current_family_count": str(len(current)),
            "current_exact_occurrences": str(sum(
                int(item["occurrence_count"]) for item in current
            )),
            "historical_only_families": str(len(families) - len(current)),
        })
    aligned_by_identity = {
        (
            item["volume"], item["page"], item["line"], item["token_index"]
        ): item for item in aligned_rows
    }
    final_reconciliation = read(
        ROOT / "data/final_ng_vs_general_signature_reconciliation.tsv"
    )
    final_ng_active_summary: list[dict[str, str]] = []
    queue_by_family = {
        (item["tibetan_syllable"], item["current_source"]): item
        for item in queue
    }
    for disposition in sorted({
        item["effective_disposition"] for item in final_reconciliation
    }):
        items = [
            item for item in final_reconciliation
            if item["effective_disposition"] == disposition
        ]
        extant = sum(
            1 for item in items
            if aligned_by_identity.get((
                item["volume"], item["page"], item["line"],
                item["token_index"],
            ), {}).get("latin_token") == item["source_token"]
        )
        extant_items = [
            item for item in items
            if aligned_by_identity.get((
                item["volume"], item["page"], item["line"],
                item["token_index"],
            ), {}).get("latin_token") == item["source_token"]
        ]

        def gate_count(field: str) -> int:
            return sum(
                queue_by_family.get(
                    (item["tibetan_syllable"], item["source_token"]), {}
                ).get(field) == "yes"
                for item in extant_items
            )
        final_ng_active_summary.append({
            "effective_disposition": disposition,
            "historical_diagnostic_rows": str(len(items)),
            "current_extant_source_rows": str(extant),
            "historical_only_rows": str(len(items) - extant),
            "current_target_ready_rows": str(
                gate_count("target_authority_ready")
            ),
            "current_signature_ready_rows": str(
                gate_count("ocr_signature_ready")
            ),
            "current_alignment_ready_rows": str(
                gate_count("alignment_ready")
            ),
            "current_domain_ready_rows": str(gate_count("domain_ready")),
            "current_final_action_ready_rows": str(
                gate_count("final_action_ready")
            ),
        })
    hypothetical_by_id = {
        row["signature_id"]: row for row in hypothetical_d_scope
    }
    structural_child_evidence: list[dict[str, str]] = []
    for record in registry_rows:
        decision = decision_map.get(record["signature_id"], {})
        if not record["parent_signature"] or not decision:
            continue
        scope = hypothetical_by_id.get(record["signature_id"], {})
        identities = [
            item for item in scope.get("matched_identities", "").split(";")
            if item and item != "none"
        ]
        volumes = sorted({item.split(":", 1)[0] for item in identities})
        pages_by_volume: dict[str, list[int]] = defaultdict(list)
        for item in identities:
            parts = item.split(":")
            if len(parts) > 1 and parts[1].isdigit():
                pages_by_volume[parts[0]].append(int(parts[1]))
        supported_same_tibetan = set()
        for item in identities:
            parts = item.split(":")
            if len(parts) < 6 or "→" not in parts[5]:
                continue
            tibetan = parts[4]
            _source, target = parts[5].split("→", 1)
            if any(
                concordance_row["tibetan_syllable"] == tibetan
                and concordance_row["latin_form"] == target
                and int(
                    concordance_row.get(
                        "independent_teaching_occurrences", "0"
                    )
                ) > 0
                for concordance_row in concordance
            ):
                supported_same_tibetan.add(tibetan)
        structural_child_evidence.append({
            "signature_child_id": record["signature_id"],
            "parent_operation": record["parent_signature"],
            "decision": decision["decision"],
            "current_exact_rows": scope.get("condition_matches", "0"),
            "distinct_syllables": scope.get("distinct_syllables", "0"),
            "reviewed_support": record["conditioned_reviewed_support"],
            "exact_alternate_support":
                record["conditioned_alternate_support"],
            "same_tibetan_independent_target_support": str(
                len(supported_same_tibetan)
            ),
            "source_volumes": ";".join(volumes),
            "source_page_ranges": ";".join(
                f"{volume}:{min(pages)}-{max(pages)}"
                for volume, pages in sorted(pages_by_volume.items()) if pages
            ),
            "line_zones": "exact_headword_gate_applied",
            "parent_reviewed_support":
                record["parent_operation_reviewed_support"],
            "parent_alternate_support":
                record["parent_operation_alternate_support"],
            "global_source_controls":
                record["parent_operation_global_controls"],
            "structural_gate_controls": record["conditioned_controls"],
            "same_tibetan_competing_controls": "0",
            "domain_controls": scope.get("failure_reasons", ""),
            "reviewed_contradictions": record["conditioned_conflicts"],
            "disposition": (
                "remain_D_no_independent_conditioned_witness_or_review"
                if decision["decision"] == "D"
                and record["conditioned_reviewed_support"] == "0"
                and record["conditioned_alternate_support"] == "0"
                else "persistent_" + decision["decision"]
            ),
        })
    return {
        "evidence": evidence, "controls": control_rows,
        "registry": registry_rows, "queue": queue, "exhaustion": exhaustion,
        "incomplete": incomplete, "moderate": moderate, "packet": packet,
        "boundary": boundary_audit,
        "condition_backtest": condition_backtest,
        "edit_attribution": edit_attributions,
        "alignment_rescue": alignment_rescue,
        "hypothetical_d_scope": hypothetical_d_scope,
        "alignment_rescue_exact": alignment_rescue_exact,
        "active_queue_summary": active_queue_summary,
        "final_ng_active_summary": final_ng_active_summary,
        "structural_alternates": structural_alternates,
        "correction_authority": correction_authority,
        "correction_authority_fields": correction_authority_fields,
        "structural_child_evidence": structural_child_evidence,
    }


def main() -> None:
    outputs = build()
    targets = [
        ("tibetan_latin_reviewed_signature_evidence.tsv", "evidence", EVIDENCE_FIELDS),
        ("tibetan_latin_ocr_signature_controls.tsv", "controls", CONTROL_FIELDS),
        ("tibetan_latin_ocr_signature_registry.tsv", "registry", REGISTRY_FIELDS),
        ("tibetan_latin_authoritative_outlier_queue.tsv", "queue", QUEUE_FIELDS),
        ("tibetan_latin_authorized_signature_exhaustion_audit.tsv", "exhaustion", EXHAUSTION_FIELDS),
        ("tibetan_latin_incomplete_final_ng_canonical_audit.tsv", "incomplete", INCOMPLETE_FIELDS),
        ("tibetan_latin_moderate_promotion_queue.tsv", "moderate", MODERATE_FIELDS),
        ("tibetan_latin_signature_review_packet.tsv", "packet", PACKET_FIELDS),
        ("tibetan_latin_token_boundary_audit.tsv", "boundary", BOUNDARY_FIELDS),
        ("tibetan_latin_signature_condition_backtest.tsv", "condition_backtest", CONDITION_BACKTEST_FIELDS),
        ("tibetan_latin_ocr_edit_span_attribution.tsv", "edit_attribution", EDIT_ATTRIBUTION_FIELDS),
        ("tibetan_latin_alignment_rescue_queue.tsv", "alignment_rescue", ALIGNMENT_RESCUE_FIELDS),
        ("tibetan_latin_signature_hypothetical_d_scope.tsv", "hypothetical_d_scope", HYPOTHETICAL_D_SCOPE_FIELDS),
        ("tibetan_latin_alignment_rescue_exact.tsv", "alignment_rescue_exact", ALIGNMENT_RESCUE_EXACT_FIELDS),
        ("tibetan_latin_active_historical_queue_summary.tsv", "active_queue_summary", ACTIVE_QUEUE_SUMMARY_FIELDS),
        ("final_ng_active_historical_summary.tsv", "final_ng_active_summary", FINAL_NG_ACTIVE_SUMMARY_FIELDS),
        ("tibetan_latin_structural_alternate_witness_evidence.tsv", "structural_alternates", STRUCTURAL_ALTERNATE_FIELDS),
        ("tibetan_latin_structural_ocr_child_evidence.tsv", "structural_child_evidence", STRUCTURAL_CHILD_EVIDENCE_FIELDS),
    ]
    for name, key, fields in targets:
        write(ROOT / "data" / name, outputs[key], fields)
    if outputs["correction_authority"]:
        write(
            ROOT / "data/tibetan_transcription_correction_authority.tsv",
            outputs["correction_authority"],
            outputs["correction_authority_fields"],
        )
    print(" ".join(f"{key}={len(outputs[key])}" for _, key, _ in targets))


if __name__ == "__main__":
    main()
