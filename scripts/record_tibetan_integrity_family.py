#!/usr/bin/env python3
"""Record one exact Tibetan-syllable transcription-integrity family."""

from __future__ import annotations

import argparse
import csv
import importlib.util
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
            "canonical_reviewed", "canonical_independent_strong"
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
            "canonical_independent_strong"
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
    args = parser.parse_args()
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
        if diagnostic["domain_context"] != "ordinary_tibetan_lexical_or_compound":
            continue
        selected.append(row)
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
            "reason": (
                "reviewed_tibetan_exact_manual_multi_error"
                if args.explicit_manual_review
                else args.reason
            ),
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
    print(f"recorded={len(selected)}")


if __name__ == "__main__":
    main()
