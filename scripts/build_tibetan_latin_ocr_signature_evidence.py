#!/usr/bin/env python3
"""Build reviewed, non-circular OCR-signature evidence and action queues."""

from __future__ import annotations

import csv
import importlib.util
import json
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
    "tibetan_role_condition", "applicable_domain",
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
    "signature_statuses", "action_category", "domain_breakdown",
    "damage_or_marker", "canonical_evidence", "sample_contexts",
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
    "reviewed_support", "alternate_witness_support", "controls",
    "tibetan_syllable", "source", "canonical_target", "target_evidence",
    "domain", "context", "suggested_decision",
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


def decisions() -> dict[str, dict[str, str]]:
    path = ROOT / "data/reviewed_tibetan_ocr_signature_decisions.tsv"
    return {row["signature"]: row for row in read(path)} if path.exists() else {}


def build() -> dict[str, list[dict[str, str]]]:
    evidence, positives, negatives = reviewed_evidence()
    alternate = alternate_support()
    outliers = read(ROOT / "data/tibetan_latin_transcription_outliers.tsv")
    canon_rows = read(ROOT / "data/tibetan_latin_canonical_syllables.tsv")
    canon_by_syllable = {r["tibetan_syllable"]: r for r in canon_rows}
    concordance = read(ROOT / "data/tibetan_latin_syllable_concordance.tsv")
    decision_map = decisions()

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
                    if decision["role_domain_condition"]
                    not in {"", "exact_tibetan_canonical_target"}
                    else "authorized"
                ),
                "D": "candidate_review", "R": "rejected",
            }[decision["decision"]]
            rationale = decision["evidence_summary"]
            evidence_tier = "persistent_reviewed_decision"
            condition = decision["role_domain_condition"]
        else:
            status = "diagnostic_only"
            condition = ""
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
            "tibetan_role_condition": condition,
            "applicable_domain": "ordinary_tibetan_lexical_or_compound",
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

    registry_by_signature = {
        row["operation_signature"]: row for row in registry_rows
    }
    queue: list[dict[str, str]] = []
    for row in outliers:
        signatures = [s for s in row["edit_signatures"].split(";") if s]
        statuses = [
            registry_by_signature.get(s, {}).get(
                "authorization_status", "diagnostic_only"
            ) for s in signatures
        ]
        safe_domain = (
            row["domain_breakdown"]
            and all(
                part.startswith("ordinary_tibetan_lexical_or_compound:")
                for part in row["domain_breakdown"].split(";")
            )
        )
        clean = row["damage_or_marker"] == "damage:0;marker:0"
        authorized = {
            "authorized", "authorized_role_conditioned",
            "authorized_domain_conditioned",
        }
        if not safe_domain:
            action = "domain_risk"
        elif not clean:
            action = "alignment_or_damage"
        elif signatures and all(status in authorized for status in statuses):
            action = "ready_all_edits_authorized"
        elif sum(status not in authorized for status in statuses) == 1:
            action = "one_signature_missing"
        elif signatures:
            action = "multiple_signatures_missing"
        else:
            action = "complex_unexplained"
        queue.append({
            "tibetan_syllable": row["tibetan_syllable"],
            "current_source": row["current_source"],
            "canonical_target": row["canonical_forms"],
            "canonical_confidence_tier": row["canonical_confidence_tier"],
            "occurrence_count": row["occurrence_count"],
            "edit_signatures": row["edit_signatures"],
            "signature_statuses": ";".join(statuses),
            "action_category": action,
            "domain_breakdown": row["domain_breakdown"],
            "damage_or_marker": row["damage_or_marker"],
            "canonical_evidence": row["canonical_evidence"],
            "sample_contexts": row["sample_contexts"],
        })

    authorized_signatures = {
        sig for sig, row in registry_by_signature.items()
        if row["authorization_status"].startswith("authorized")
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
                if tier in {"canonical_reviewed", "canonical_independent_strong"}
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
        reg = registry_by_signature.get(signature, {})
        control = next(
            (r for r in control_rows if r["signature"] == signature), {}
        )
        for row in examples[signature][:20]:
            packet.append({
                "signature": signature, "expected_clean_yield": str(expected),
                "expected_syllable_yield": str(len(syllable_yields[signature])),
                "reviewed_support": reg.get(
                    "reviewed_supporting_occurrences", "0"
                ),
                "alternate_witness_support": reg.get(
                    "alternate_witness_support", "0"
                ),
                "controls": control.get(
                    "legitimate_source_form_controls", "0"
                ),
                "tibetan_syllable": row["tibetan_syllable"],
                "source": row["current_source"],
                "canonical_target": row["canonical_target"],
                "target_evidence": row["canonical_evidence"],
                "domain": row["domain_breakdown"],
                "context": row["sample_contexts"],
                "suggested_decision": "manual_signature_review",
            })
    return {
        "evidence": evidence, "controls": control_rows,
        "registry": registry_rows, "queue": queue, "exhaustion": exhaustion,
        "incomplete": incomplete, "moderate": moderate, "packet": packet,
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
    ]
    for name, key, fields in targets:
        write(ROOT / "data" / name, outputs[key], fields)
    print(" ".join(f"{key}={len(outputs[key])}" for _, key, _ in targets))


if __name__ == "__main__":
    main()
