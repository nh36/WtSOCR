#!/usr/bin/env python3
"""Record one exact Tibetan-syllable transcription-integrity family."""

from __future__ import annotations

import argparse
import hashlib
import json
import csv
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_tibetan_latin_integrity.py"
SPEC = importlib.util.spec_from_file_location("tibetan_latin_integrity", SCRIPT)
assert SPEC and SPEC.loader
integrity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = integrity
SPEC.loader.exec_module(integrity)
SIGNATURE_SCRIPT = ROOT / "scripts/build_tibetan_latin_ocr_signature_evidence.py"
SIGNATURE_SPEC = importlib.util.spec_from_file_location(
    "tibetan_ocr_signature_authorization", SIGNATURE_SCRIPT
)
assert SIGNATURE_SPEC and SIGNATURE_SPEC.loader
signature_engine = importlib.util.module_from_spec(SIGNATURE_SPEC)
sys.modules[SIGNATURE_SPEC.name] = signature_engine
SIGNATURE_SPEC.loader.exec_module(signature_engine)


def validate_authorization(
    tibetan: str, sources: set[str], target: str,
    explicit_manual_review: bool,
) -> None:
    if explicit_manual_review:
        return
    canonical_rows = integrity.read_tsv(
        ROOT / "data/tibetan_latin_canonical_syllables.tsv"
    )
    canonical = next((
        row for row in canonical_rows
        if row["tibetan_syllable"] == tibetan
        and target in row["canonical_forms"].split(";")
        and row.get("canonical_confidence_tier") in {
            "canonical_reviewed", "canonical_independent_strong",
            "canonical_feature_composed",
        }
    ), None)
    signatures = {
        row["operation_signature"]
        for row in integrity.read_tsv(
            ROOT / "data/tibetan_latin_ocr_signature_registry.tsv"
        )
        if row["authorization_status"] in {
            "authorized", "authorized_role_conditioned",
            "authorized_domain_conditioned",
        }
    }
    concordance_path = (
        ROOT / "scripts/build_tibetan_latin_syllable_concordance.py"
    )
    spec = importlib.util.spec_from_file_location(
        "canonical_engine_for_recorder", concordance_path
    )
    assert spec and spec.loader
    canonical_engine = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = canonical_engine
    spec.loader.exec_module(canonical_engine)
    if canonical is None:
        raise ValueError(
            "Target is not canonical_reviewed or "
            "canonical_independent_strong/canonical_feature_composed"
        )
    if canonical["canonical_confidence_tier"] == "canonical_feature_composed":
        if canonical.get("feature_leave_one_out_status") != "passed":
            raise ValueError("Feature-composed target lacks leave-one-out support")
        historically_authorised_features = {
            row["rule_id"] for row in integrity.read_tsv(
                ROOT / "data/reviewed_tibetan_feature_mapping_decisions.tsv"
            ) if row["decision"] == "A"
        }
        currently_revalidated_features = {
            row["rule_id"] for row in integrity.read_tsv(
                ROOT / "data/tibetan_feature_mapping_revalidation.tsv"
            ) if row["effective_authority"] == "yes"
        }
        authorised_features = (
            historically_authorised_features
            & currently_revalidated_features
        )
        dependencies = {
            item for item in canonical.get(
                "feature_dependency_rule_ids", ""
            ).split(";") if item
        }
        if not dependencies or not dependencies <= authorised_features:
            raise ValueError(
                "Feature-composed target has missing/deferred dependencies"
            )
    for source in sources:
        operations = canonical_engine.edit_operations(source, target)
        unsupported = [
            op["signature"] for op in operations
            if op["signature"] not in signatures
        ]
        if unsupported:
            raise ValueError(
                f"Unsupported confusion signatures for {source}: "
                f"{unsupported}"
            )


def require_occurrence_identity_evidence(
    reason: str, explicit_manual_review: bool, evidence: str | None,
) -> None:
    if (
        explicit_manual_review
        and reason == "reviewed_tibetan_exact_manual_structural_root_ocr"
        and not evidence
    ):
        raise ValueError(
            "Root-changing Latin review requires occurrence-level Tibetan "
            "identity evidence"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tibetan", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument(
        "--reason", default="reviewed_tibetan_exact_ocr_signature"
    )
    parser.add_argument("--explicit-manual-review", action="store_true")
    parser.add_argument(
        "--occurrence-identity-evidence",
        help=(
            "Required for a manually reviewed Latin root-span substitution; "
            "cite lemma order, an exact sibling, or an exact repeated identity."
        ),
    )
    args = parser.parse_args()
    require_occurrence_identity_evidence(
        args.reason, args.explicit_manual_review,
        args.occurrence_identity_evidence,
    )
    sources = set(args.sources.split(","))
    validate_authorization(
        args.tibetan, sources, args.target, args.explicit_manual_review
    )
    aligned = integrity.collect_all_aligned(ROOT / "release/current")
    diagnostics = integrity.build_diagnostics(ROOT / "release/current")
    reviewed_echo_keys = signature_engine.reviewed_echo_identity_keys()
    by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in diagnostics
    }
    selected: list[dict[str, str]] = []
    for row in aligned:
        if (
            row["tibetan_syllable"] != args.tibetan
            or row["latin_token"] not in sources
        ):
            continue
        key = (row["volume"], row["page"], row["line"], row["token_index"])
        if key in reviewed_echo_keys:
            continue
        diagnostic = by_key[key]
        if diagnostic["alignment_confidence"] not in {
            "secure_positional_alignment", "secure_reviewed_alignment",
        }:
            continue
        if row["damage_scope"] not in {"none", "later_gloss_or_commentary"}:
            continue
        if row["marker_attached"] == "yes":
            continue
        if row["token_boundary_status"] != "token_boundary_secure":
            continue
        selected_row = dict(row)
        selected_row["_alignment_confidence"] = diagnostic[
            "alignment_confidence"
        ]
        selected.append(selected_row)
    if not selected:
        raise ValueError("No secure exact identities selected")
    if not args.explicit_manual_review:
        registry: dict[str, list[dict[str, str]]] = {}
        for registry_row in integrity.read_tsv(
            ROOT / "data/tibetan_latin_ocr_signature_registry.tsv"
        ):
            registry.setdefault(
                registry_row["operation_signature"], []
            ).append(registry_row)
        for row in selected:
            for operation in signature_engine.canonical.edit_operations(
                row["latin_token"], args.target
            ):
                records = [
                    record for record in registry[operation["signature"]]
                    if record["authorization_status"] in {
                        "authorized", "authorized_role_conditioned",
                        "authorized_domain_conditioned",
                    }
                ]
                results = [
                    signature_engine.signature_applies_to_row(
                        record, row, args.target
                    ) for record in records
                ]
                if not any(applies for applies, _reason in results):
                    reason = results[0][1] if results else "not_authorized"
                    raise ValueError(
                        f"Signature condition mismatch for "
                        f"{operation['signature']} at {row['volume']} "
                        f"{row['page']}:{row['line']} token "
                        f"{row['token_index']}: {reason}"
                    )
    path = integrity.OVERRIDES_PATH
    rows = integrity.read_tsv(path)
    fields = list(rows[0])
    existing = {
        (r["volume"], r["page"], r["line"], r["token_index"], r["from_token"])
        for r in rows
    }
    for row in selected:
        key = (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["latin_token"],
        )
        if key in existing:
            raise ValueError(f"Exact identity already reviewed: {key}")
        rows.append({
            "volume": row["volume"], "page": row["page"],
            "line": row["line"], "token_index": row["token_index"],
            "from_token": row["latin_token"], "to_token": args.target,
            "reason": args.reason,
            "evidence": args.evidence,
            "review_note": (
                f"Exact {args.tibetan} alignment; canonical target and "
                "conditioned reviewed OCR signature; no Latin-wide substitution."
            ),
        })
    rows.sort(key=lambda r: (
        r["volume"], int(r["page"]), int(r["line"]),
        int(r["token_index"]), r["from_token"],
    ))
    integrity.write_tsv(path, rows, fields)
    decision_path = (
        ROOT / "data/tibetan_transcription_correction_decisions.tsv"
    )
    decision_fields = [
        "volume", "page", "line", "token_index", "tibetan_syllable",
        "observed_source", "target", "decision_base_sha",
        "canonical_tier", "canonical_target", "component_feature_rule_ids",
        "structural_rule_ids", "ocr_signature_ids",
        "edit_structural_attribution", "signature_decision_version",
        "gate0_alignment_status", "token_boundary_status", "domain",
        "prior_decision_state", "target_support_channel", "evidence",
    ]
    decision_rows = (
        integrity.read_tsv(decision_path) if decision_path.exists() else []
    )
    canonical_row = next(
        row for row in integrity.read_tsv(
            ROOT / "data/tibetan_latin_canonical_syllables.tsv"
        )
        if row["tibetan_syllable"] == args.tibetan
        and args.target in row["canonical_forms"].split(";")
    )
    registry_rows = integrity.read_tsv(
        ROOT / "data/tibetan_latin_ocr_signature_registry.tsv"
    )
    spans = [
        row for row in integrity.read_tsv(
            ROOT / "data/tibetan_latin_canonical_role_spans.tsv"
        )
        if row["tibetan_syllable"] == args.tibetan
        and row["target"] == args.target
    ]
    base_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    for row in selected:
        operation_ids = []
        attributions = []
        versions = []
        for operation in signature_engine.canonical.edit_operations(
            row["latin_token"], args.target
        ):
            matching = []
            for record in registry_rows:
                if (
                    record["operation_signature"] == operation["signature"]
                    and record["authorization_status"].startswith("authorized")
                    and signature_engine.signature_applies_to_row(
                        record, row, args.target
                    )[0]
                ):
                    matching.append(record)
            operation_ids.append(
                matching[0]["signature_id"] if matching
                else "exact_row_review_only"
            )
            attribution = signature_engine.attribute_edit_to_spans(
                row["latin_token"], args.target, operation, spans,
                integrity.classify_domain(
                    row.get("zone", ""), row.get("context_excerpt", "")
                ),
            )
            attributions.append(
                attribution["source_structural_location"] + "→"
                + attribution["target_structural_role"]
            )
            versions.append(
                hashlib.sha256(json.dumps(
                    matching[0] if matching else {
                        "authority": "explicit_manual_review"
                    },
                    sort_keys=True, ensure_ascii=False,
                ).encode("utf-8")).hexdigest()[:16]
            )
        decision_rows.append({
            "volume": row["volume"], "page": row["page"],
            "line": row["line"], "token_index": row["token_index"],
            "tibetan_syllable": args.tibetan,
            "observed_source": row["latin_token"], "target": args.target,
            "decision_base_sha": base_sha,
            "canonical_tier": canonical_row["canonical_confidence_tier"],
            "canonical_target": canonical_row["canonical_forms"],
            "component_feature_rule_ids": canonical_row.get(
                "feature_dependency_rule_ids", ""
            ),
            "structural_rule_ids": "",
            "ocr_signature_ids": ";".join(operation_ids),
            "edit_structural_attribution": ";".join(attributions),
            "signature_decision_version": ";".join(versions),
            "gate0_alignment_status": row["_alignment_confidence"],
            "token_boundary_status": row["token_boundary_status"],
            "domain": integrity.classify_domain(
                row.get("zone", ""), row.get("context_excerpt", "")
            ),
            "prior_decision_state": (
                "none_after_exact_decision_precedence_check"
            ),
            "target_support_channel": canonical_row.get(
                "evidence_class", ""
            ),
            "evidence": args.evidence,
        })
    integrity.write_tsv(
        decision_path, decision_rows, decision_fields
    )
    if (
        args.explicit_manual_review
        and args.reason == "reviewed_tibetan_exact_manual_structural_root_ocr"
    ):
        identity_path = (
            ROOT / "data/reviewed_tibetan_occurrence_identity_checks.tsv"
        )
        identity_fields = [
            "volume", "page", "line", "token_index", "observed_tibetan",
            "adjudicated_tibetan", "latin_source", "latin_target",
            "root_change", "identity_status", "evidence_channel",
            "evidence", "review_batch",
        ]
        identity_rows = (
            integrity.read_tsv(identity_path) if identity_path.exists() else []
        )
        existing_identity = {
            (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["latin_source"], row["latin_target"],
            )
            for row in identity_rows
        }
        for row in selected:
            identity_key = (
                row["volume"], row["page"], row["line"],
                row["token_index"], row["latin_token"], args.target,
            )
            if identity_key in existing_identity:
                continue
            identity_rows.append({
                "volume": row["volume"], "page": row["page"],
                "line": row["line"], "token_index": row["token_index"],
                "observed_tibetan": args.tibetan,
                "adjudicated_tibetan": args.tibetan,
                "latin_source": row["latin_token"],
                "latin_target": args.target,
                "root_change": "yes",
                "identity_status": "retain_latin_correction",
                "evidence_channel": "explicit_occurrence_identity_review",
                "evidence": args.occurrence_identity_evidence,
                "review_batch": args.evidence,
            })
        integrity.write_tsv(identity_path, identity_rows, identity_fields)
    print(f"recorded={len(selected)}")


if __name__ == "__main__":
    main()
