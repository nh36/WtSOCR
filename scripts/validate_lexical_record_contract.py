#!/usr/bin/env python3
"""Validate a source-faithful future lexical-record JSONL export.

This is a contract validator, not a parser.  It deliberately keeps the WTS's
historical Library of Congress (LoC) transliteration distinct from Wylie and
keeps print-faithful and BAdW editorial readings as separate layers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


CONTRACT_VERSION = "wts-lexical-record-v2"
RECORD_TYPES = {"entry", "sense", "attestation", "citation", "bibliographic_source", "cross_reference", "editorial_variant"}
LAYERS = {"print_faithful", "badw_editorial"}
VARIANT_KINDS = {"post_print_editorial_revision", "print_variant", "presentation", "unresolved"}
PRINT_CHECKS = {"not_required", "matches_badw", "differs_from_badw", "ambiguous", "pending"}
ASSOCIATION_STATUSES = {"explicit", "entry_level", "unresolved"}
AUTHORITY_STATUSES = {"resolved", "unresolved", "ambiguous", "not_applicable"}
CROSS_REFERENCE_STATUSES = {"resolved", "unresolved"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _error(errors: list[str], line: int, message: str) -> None:
    errors.append(f"line {line}: {message}")


def _positive(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _source_spans(value: Any, line: int, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        _error(errors, line, "source_spans must be a non-empty array")
        return
    for index, span in enumerate(value):
        if not isinstance(span, dict):
            _error(errors, line, f"source_spans[{index}] must be an object")
            continue
        for field in ("source_id", "source_sha256", "field", "start", "end"):
            if field not in span:
                _error(errors, line, f"source_spans[{index}] lacks {field}")
        if not isinstance(span.get("source_id"), str) or not span.get("source_id"):
            _error(errors, line, f"source_spans[{index}].source_id must be non-empty")
        if not isinstance(span.get("field"), str) or not span.get("field"):
            _error(errors, line, f"source_spans[{index}].field must be non-empty")
        if not isinstance(span.get("source_sha256"), str) or not SHA256.fullmatch(span.get("source_sha256", "")):
            _error(errors, line, f"source_spans[{index}].source_sha256 must be lowercase SHA-256")
        start, end = span.get("start"), span.get("end")
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            _error(errors, line, f"source_spans[{index}].start must be non-negative integer")
        if not isinstance(end, int) or isinstance(end, bool) or not isinstance(start, int) or end <= start:
            _error(errors, line, f"source_spans[{index}].end must be greater than start")


def validate(records: Iterable[dict[str, Any]]) -> list[str]:
    """Return deterministic contract errors, including cross-record references."""
    errors: list[str] = []
    ids: dict[str, tuple[int, dict[str, Any]]] = {}
    rows = list(records)
    for line, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            _error(errors, line, "record must be an object")
            continue
        if row.get("contract_version") != CONTRACT_VERSION:
            _error(errors, line, f"contract_version must be {CONTRACT_VERSION}")
        record_type = row.get("record_type")
        if record_type not in RECORD_TYPES:
            _error(errors, line, f"record_type must be one of {sorted(RECORD_TYPES)}")
        record_id = row.get("id")
        if not isinstance(record_id, str) or not record_id:
            _error(errors, line, "id must be a non-empty string")
        elif record_id in ids:
            _error(errors, line, f"duplicate id {record_id!r}; first used on line {ids[record_id][0]}")
        else:
            ids[record_id] = (line, row)
        _source_spans(row.get("source_spans"), line, errors)
        for field in ("source_snapshot_id", "extraction_run_id"):
            if not isinstance(row.get(field), str) or not row.get(field):
                _error(errors, line, f"{field} must be a non-empty string")
        if record_type == "entry":
            if row.get("layer") not in LAYERS:
                _error(errors, line, "entry layer must be print_faithful or badw_editorial")
            headword = row.get("headword")
            if not isinstance(headword, dict) or not isinstance(headword.get("loc"), str) or not isinstance(headword.get("tibetan"), str):
                _error(errors, line, "entry headword must contain string loc and tibetan fields")
            if not isinstance(row.get("witness_ids"), list) or not all(isinstance(x, str) and x for x in row.get("witness_ids", [])):
                _error(errors, line, "entry witness_ids must be an array of non-empty strings")
        elif record_type == "sense":
            if not isinstance(row.get("entry_id"), str) or not _positive(row.get("ordinal")) or not isinstance(row.get("definition"), str):
                _error(errors, line, "sense requires entry_id, positive ordinal, and string definition")
        elif record_type == "attestation":
            if (not isinstance(row.get("entry_id"), str) or not _positive(row.get("ordinal"))
                    or not isinstance(row.get("tibetan"), str) or row.get("association_status") not in ASSOCIATION_STATUSES):
                _error(errors, line, "attestation requires entry_id, positive ordinal, string tibetan, and allowed association_status")
            sense_id = row.get("sense_id")
            if sense_id is not None and not isinstance(sense_id, str):
                _error(errors, line, "attestation sense_id must be a string when supplied")
            if row.get("association_status") == "explicit" and not isinstance(sense_id, str):
                _error(errors, line, "explicit attestation association requires sense_id")
            if row.get("association_status") != "explicit" and sense_id is not None:
                _error(errors, line, "non-explicit attestation association must not supply sense_id")
            if "german_translation" in row and not isinstance(row["german_translation"], str):
                _error(errors, line, "attestation german_translation must be a string when supplied")
            citation_ids = row.get("citation_ids")
            if not isinstance(citation_ids, list) or not all(isinstance(item, str) and item for item in citation_ids):
                _error(errors, line, "attestation citation_ids must be an array of non-empty strings")
        elif record_type == "citation":
            if (not isinstance(row.get("entry_id"), str) or not isinstance(row.get("raw_text"), str)
                    or not row.get("raw_text") or row.get("authority_status") not in AUTHORITY_STATUSES):
                _error(errors, line, "citation requires entry_id, non-empty raw_text, and allowed authority_status")
            if "siglum" in row and (not isinstance(row["siglum"], str) or not row["siglum"]):
                _error(errors, line, "citation siglum must be a non-empty string when supplied")
            authority_id = row.get("bibliographic_source_id")
            if row.get("authority_status") == "resolved" and not isinstance(authority_id, str):
                _error(errors, line, "resolved citation requires bibliographic_source_id")
            if row.get("authority_status") != "resolved" and authority_id is not None:
                _error(errors, line, "unresolved, ambiguous, or not_applicable citation must not supply bibliographic_source_id")
        elif record_type == "bibliographic_source":
            if not isinstance(row.get("canonical_label"), str) or not row.get("canonical_label"):
                _error(errors, line, "bibliographic_source requires canonical_label")
        elif record_type == "cross_reference":
            if (not isinstance(row.get("entry_id"), str) or row.get("marker") not in {"↑", "↓"}
                    or row.get("resolution_status") not in CROSS_REFERENCE_STATUSES):
                _error(errors, line, "cross_reference requires entry_id, literal arrow marker, and allowed resolution_status")
            target_url = row.get("target_url")
            if row.get("resolution_status") == "resolved" and not isinstance(target_url, str):
                _error(errors, line, "resolved cross_reference requires target_url")
            if row.get("resolution_status") == "unresolved" and target_url is not None:
                _error(errors, line, "unresolved cross_reference must not supply target_url")
            if "target_label" in row and not isinstance(row["target_label"], str):
                _error(errors, line, "cross_reference target_label must be a string when supplied")
        elif record_type == "editorial_variant":
            if (not isinstance(row.get("entry_id"), str) or not isinstance(row.get("field_path"), str)
                    or not isinstance(row.get("base_reading"), str) or not isinstance(row.get("variant_reading"), str)
                    or row.get("variant_kind") not in VARIANT_KINDS or row.get("print_check_status") not in PRINT_CHECKS):
                _error(errors, line, "editorial_variant requires entry_id, field_path, readings, allowed kind, and print-check status")
    expected = {"entry_id": "entry", "sense_id": "sense", "bibliographic_source_id": "bibliographic_source"}
    for line, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        for field, kind in expected.items():
            target = row.get(field)
            if target is None:
                continue
            if target not in ids:
                _error(errors, line, f"{field} {target!r} does not exist")
            elif ids[target][1].get("record_type") != kind:
                _error(errors, line, f"{field} {target!r} is not a {kind}")
        for citation_id in row.get("citation_ids", []):
            if citation_id not in ids:
                _error(errors, line, f"citation_ids {citation_id!r} does not exist")
            elif ids[citation_id][1].get("record_type") != "citation":
                _error(errors, line, f"citation_ids {citation_id!r} is not a citation")
        if row.get("record_type") == "attestation" and isinstance(row.get("sense_id"), str):
            sense = ids.get(row["sense_id"])
            if sense and sense[1].get("entry_id") != row.get("entry_id"):
                _error(errors, line, "attestation sense_id belongs to a different entry")
    return errors


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    # Iterating the file (rather than str.splitlines()) retains U+2028/U+2029
    # inside otherwise valid source-faithful JSON strings.
    with path.open(encoding="utf-8") as handle:
        for line_no, text in enumerate(handle, 1):
            if not text.strip():
                continue
            try:
                records.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_no}: invalid JSON: {exc.msg}") from exc
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(read_jsonl(args.jsonl))
    except ValueError as exc:
        print(str(exc))
        return 2
    report = {"contract_version": CONTRACT_VERSION, "input_sha256": hashlib.file_digest(args.jsonl.open("rb"), "sha256").hexdigest(), "valid": not errors, "errors": errors}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
