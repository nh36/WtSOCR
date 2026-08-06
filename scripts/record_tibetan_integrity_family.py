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


OCCURRENCE_IDENTITY_CHANNELS = integrity.OCCURRENCE_IDENTITY_CHANNELS


def root_change_status(
    attributions: list[dict[str, str]],
) -> str:
    """Classify actual edit spans without consulting the reason code."""
    for attribution in attributions:
        roles = set(attribution["target_structural_role"].split(";"))
        if "root_consonant" in roles:
            return "yes"
    for attribution in attributions:
        if (
            attribution["attribution_status"] == "structurally_unresolved"
            or attribution["extra_source_material"] == "yes"
        ):
            return "unresolved"
    return "no"


def require_occurrence_identity_evidence(
    explicit_manual_review: bool,
    attribution_status: str,
    root_change_declaration: str | None,
    evidence_channel: str | None,
    evidence: str | None,
) -> bool:
    """Fail closed for manual root edits, including multi-error repairs."""
    if not explicit_manual_review:
        return False
    if attribution_status == "unresolved" and root_change_declaration is None:
        raise ValueError(
            "Unresolved manual edit attribution requires an explicit "
            "--root-change yes/no declaration"
        )
    root_change = (
        attribution_status == "yes" or root_change_declaration == "yes"
    )
    if root_change:
        if evidence_channel not in OCCURRENCE_IDENTITY_CHANNELS:
            raise ValueError(
                "Root-changing Latin review requires a controlled, "
                "independent occurrence-identity evidence channel"
            )
        if not evidence:
            raise ValueError(
                "Root-changing Latin review requires occurrence-level "
                "Tibetan identity evidence"
            )
    return root_change


def exact_coordinate_from_args(args: argparse.Namespace) -> tuple[
    str, str, str, str
] | None:
    values = (args.volume, args.page, args.line, args.token_index)
    if any(value is not None for value in values) and not all(
        value is not None for value in values
    ):
        raise ValueError(
            "Exact manual review coordinates require volume, page, line, "
            "and token index together"
        )
    return values if all(value is not None for value in values) else None


def scope_root_review_to_coordinate(
    selected: list[dict[str, str]],
    coordinate: tuple[str, str, str, str] | None,
) -> list[dict[str, str]]:
    if coordinate is None:
        raise ValueError(
            "Manual root-changing correction requires an exact "
            "volume/page/line/token coordinate"
        )
    scoped = [
        row for row in selected
        if (
            row["volume"], row["page"], row["line"], row["token_index"]
        ) == coordinate
    ]
    if len(scoped) != 1:
        raise ValueError(
            f"Exact root-review coordinate selected {len(scoped)} rows: "
            f"{coordinate}"
        )
    return scoped


def explicit_manual_review_note(
    tibetan: str,
    source: str,
    target: str,
    row: dict[str, str],
    registry_rows: list[dict[str, str]],
) -> str:
    authorities: list[str] = []
    for operation in signature_engine.canonical.edit_operations(source, target):
        matches = [
            record for record in registry_rows
            if (
                record["operation_signature"] == operation["signature"]
                and record["authorization_status"].startswith("authorized")
                and signature_engine.signature_applies_to_row(
                    record, row, target
                )[0]
            )
        ]
        authority = (
            matches[0]["signature_id"] if matches
            else "exact-row-only"
        )
        authorities.append(f"{operation['signature']}={authority}")
    return (
        f"Exact {tibetan} alignment; explicit manual review; operation "
        f"authority: {'; '.join(authorities)}; no Latin-wide substitution."
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
    parser.add_argument(
        "--occurrence-identity-channel",
        choices=sorted(OCCURRENCE_IDENTITY_CHANNELS),
    )
    parser.add_argument(
        "--root-change",
        choices=("yes", "no"),
        help=(
            "Required when structural attribution is unresolved; uncertainty "
            "must not bypass occurrence-identity review."
        ),
    )
    parser.add_argument("--volume")
    parser.add_argument("--page")
    parser.add_argument("--line")
    parser.add_argument("--token-index")
    args = parser.parse_args()
    requested_coordinate = exact_coordinate_from_args(args)
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
    spans = [
        row for row in integrity.read_tsv(
            ROOT / "data/tibetan_latin_canonical_role_spans.tsv"
        )
        if row["tibetan_syllable"] == args.tibetan
        and row["target"] == args.target
    ]
    root_change_by_identity: dict[
        tuple[str, str, str, str, str], bool
    ] = {}
    attribution_by_identity: dict[
        tuple[str, str, str, str, str], list[dict[str, str]]
    ] = {}
    for row in selected:
        identity = (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["latin_token"],
        )
        domain = integrity.classify_domain(
            row.get("zone", ""), row.get("context_excerpt", "")
        )
        attributions = [
            signature_engine.attribute_edit_to_spans(
                row["latin_token"], args.target, operation, spans, domain
            )
            for operation in signature_engine.canonical.edit_operations(
                row["latin_token"], args.target
            )
        ]
        attribution_by_identity[identity] = attributions
        root_change_by_identity[identity] = require_occurrence_identity_evidence(
            args.explicit_manual_review,
            root_change_status(attributions),
            args.root_change,
            args.occurrence_identity_channel,
            args.occurrence_identity_evidence,
        )
    if any(root_change_by_identity.values()):
        selected = scope_root_review_to_coordinate(
            selected, requested_coordinate
        )
        selected_keys = {
            (
                row["volume"], row["page"], row["line"],
                row["token_index"], row["latin_token"],
            )
            for row in selected
        }
        root_change_by_identity = {
            key: value for key, value in root_change_by_identity.items()
            if key in selected_keys
        }
        attribution_by_identity = {
            key: value for key, value in attribution_by_identity.items()
            if key in selected_keys
        }
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
    registry_rows = integrity.read_tsv(
        ROOT / "data/tibetan_latin_ocr_signature_registry.tsv"
    )
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
                explicit_manual_review_note(
                    args.tibetan, row["latin_token"], args.target,
                    row, registry_rows,
                )
                if args.explicit_manual_review else
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
    canonical_candidates = [
        row for row in integrity.read_tsv(
            ROOT / "data/tibetan_latin_canonical_syllables.tsv"
        )
        if row["tibetan_syllable"] == args.tibetan
    ]
    canonical_row = next(
        (
            row for row in canonical_candidates
            if args.target in row["canonical_forms"].split(";")
        ),
        canonical_candidates[0]
        if args.explicit_manual_review and canonical_candidates else None,
    )
    if canonical_row is None:
        raise ValueError(
            f"No canonical registry row for exact Tibetan {args.tibetan}"
        )
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
            ) if args.target in canonical_row["canonical_forms"].split(";")
            else (
                "exact_manual_lexical_identity_review"
            ),
            "evidence": args.evidence,
        })
    integrity.write_tsv(
        decision_path, decision_rows, decision_fields
    )
    if args.explicit_manual_review and any(root_change_by_identity.values()):
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
            lookup_key = (
                row["volume"], row["page"], row["line"],
                row["token_index"], row["latin_token"],
            )
            if (
                identity_key in existing_identity
                or not root_change_by_identity[lookup_key]
            ):
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
                "evidence_channel": args.occurrence_identity_channel,
                "evidence": args.occurrence_identity_evidence,
                "review_batch": args.evidence,
            })
        integrity.write_tsv(identity_path, identity_rows, identity_fields)
    print(f"recorded={len(selected)}")


if __name__ == "__main__":
    main()
