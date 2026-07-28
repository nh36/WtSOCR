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
    "source_position", "target_position", "source_context_pattern",
    "target_context_pattern", "domain_condition",
    "canonical_target_required", "exact_tibetan_required",
    "reviewed_atomic_supporting_syllables", "reviewed_supporting_occurrences",
    "reviewed_supporting_volumes", "reviewed_page_ranges",
    "historical_support", "alternate_witness_support",
    "legitimate_controls", "conflicts", "evidence_tier",
    "authorization_status", "rationale",
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
    "tibetan_syllable", "source", "canonical_target", "operation_signature",
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
    return {row["signature"]: row for row in read(path)} if path.exists() else {}


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
    if (
        signature_record.get("exact_tibetan_required") == "yes"
        and not row.get("tibetan_syllable")
    ):
        return False, "exact_tibetan_missing"
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
    operations = canonical.edit_operations(source, canonical_target)
    operation = next((
        op for op in operations
        if op["signature"] == signature_record.get("operation_signature")
    ), None)
    if operation is None:
        return False, "signature_not_in_edit_script"
    source_position = signature_record.get("source_position", "")
    target_position = signature_record.get("target_position", "")
    if source_position == "token_final" and (
        int(operation["source_position"]) + len(operation["source_span"])
        != len(source)
    ):
        return False, "source_position_mismatch"
    if target_position == "token_final" and (
        int(operation["target_position"]) + len(operation["target_span"])
        != len(canonical_target)
    ):
        return False, "target_position_mismatch"
    if source_position == "token_initial" and operation["source_position"] != "0":
        return False, "source_position_mismatch"
    if target_position == "token_initial" and operation["target_position"] != "0":
        return False, "target_position_mismatch"
    roles = integrity.tibetan_roles(row["tibetan_syllable"])
    role = signature_record.get("tibetan_role", "")
    feature = signature_record.get("tibetan_feature", "")
    if role == "suffix_coda" and roles.get("suffix_coda") != feature:
        return False, "tibetan_role_mismatch"
    if role == "root_consonant" and roles.get("root_consonant") != feature:
        return False, "tibetan_role_mismatch"
    if role == "latin_initial_confusable" and operation["source_position"] != "0":
        return False, "tibetan_role_mismatch"
    if (
        signature_record.get("canonical_target_required") == "yes"
        and not canonical_target
    ):
        return False, "canonical_target_missing"
    return True, "condition_match"


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
                        "tibetan_role", "tibetan_feature", "source_position",
                        "target_position", "source_context_pattern",
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
            "source_position": decision.get("source_position", "")
            if decision else "",
            "target_position": decision.get("target_position", "")
            if decision else "",
            "source_context_pattern": decision.get(
                "source_context_pattern", ""
            ) if decision else "",
            "target_context_pattern": decision.get(
                "target_context_pattern", ""
            ) if decision else "",
            "domain_condition": decision.get(
                "domain_condition", ""
            ) if decision else "",
            "canonical_target_required": decision.get(
                "canonical_target_required", "yes"
            ) if decision else "yes",
            "exact_tibetan_required": decision.get(
                "exact_tibetan_required", "yes"
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
            "source_position": decision.get("source_position", ""),
            "target_position": decision.get("target_position", ""),
            "source_context_pattern": decision.get(
                "source_context_pattern", ""
            ),
            "target_context_pattern": decision.get(
                "target_context_pattern", ""
            ),
            "domain_condition": decision.get("domain_condition", ""),
            "canonical_target_required": decision.get(
                "canonical_target_required", "yes"
            ),
            "exact_tibetan_required": decision.get(
                "exact_tibetan_required", "yes"
            ),
            "evidence_tier": "persistent_reviewed_conditioned_child",
            "authorization_status": {
                "A": "authorized_role_conditioned",
                "D": "candidate_review", "R": "rejected",
            }[decision["decision"]],
            "rationale": decision["evidence_summary"],
        })
        registry_rows.append(child)

    registry_by_signature: dict[str, list[dict[str, str]]] = defaultdict(list)
    for registry_row in registry_rows:
        registry_by_signature[
            registry_row["operation_signature"]
        ].append(registry_row)
    aligned_rows = integrity.collect_all_aligned(ROOT / "release/current")
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
        family_attributions = [
            {
                "tibetan_syllable": row["tibetan_syllable"],
                "source": row["current_source"],
                "canonical_target": row["canonical_forms"],
                "operation_signature": operation["signature"],
                **attribute_edit_to_spans(
                    row["current_source"], row["canonical_forms"],
                    operation, target_spans, row["domain_breakdown"],
                ),
            }
            for operation in operations
        ]
        edit_attributions.extend(family_attributions)
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
                "gated_collision_controls": "0",
                "same_tibetan_competing_controls": "0",
                "domain_controls": control.get("foreign_domain_cases", "0"),
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
    return {
        "evidence": evidence, "controls": control_rows,
        "registry": registry_rows, "queue": queue, "exhaustion": exhaustion,
        "incomplete": incomplete, "moderate": moderate, "packet": packet,
        "boundary": boundary_audit,
        "condition_backtest": condition_backtest,
        "edit_attribution": edit_attributions,
        "alignment_rescue": alignment_rescue,
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
    ]
    for name, key, fields in targets:
        write(ROOT / "data" / name, outputs[key], fields)
    print(" ".join(f"{key}={len(outputs[key])}" for _, key, _ in targets))


if __name__ == "__main__":
    main()
