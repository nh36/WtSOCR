from __future__ import annotations

import copy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_lexical_record_contract import CONTRACT_VERSION, validate  # noqa: E402


HASH = "a" * 64


def span(field: str) -> dict[str, object]:
    return {"source_id": "badw:article:example", "source_sha256": HASH, "field": field, "start": 0, "end": 1}


def corpus() -> list[dict[str, object]]:
    return [
        {"contract_version": CONTRACT_VERSION, "record_type": "entry", "id": "entry:1", "layer": "print_faithful", "headword": {"loc": "ka", "tibetan": "ཀ"}, "witness_ids": ["badw:article:example"], "source_spans": [span("lemma")]},
        {"contract_version": CONTRACT_VERSION, "record_type": "sense", "id": "sense:1", "entry_id": "entry:1", "ordinal": 1, "definition": "Bedeutung", "source_spans": [span("meaning")]},
        {"contract_version": CONTRACT_VERSION, "record_type": "bibliographic_source", "id": "bib:1", "canonical_label": "Example source", "source_spans": [span("siglum")]},
        {"contract_version": CONTRACT_VERSION, "record_type": "citation", "id": "citation:1", "siglum": "Ex", "bibliographic_source_id": "bib:1", "locator": "1.1", "source_spans": [span("citation")]},
        {"contract_version": CONTRACT_VERSION, "record_type": "attestation", "id": "attestation:1", "sense_id": "sense:1", "ordinal": 1, "tibetan": "ཀ", "german_translation": "eins", "citation_id": "citation:1", "source_spans": [span("example")]},
        {"contract_version": CONTRACT_VERSION, "record_type": "editorial_variant", "id": "variant:1", "entry_id": "entry:1", "field_path": "senses[0].definition", "base_reading": "Bedeutung", "variant_reading": "Neue Bedeutung", "variant_kind": "post_print_editorial_revision", "print_check_status": "differs_from_badw", "source_spans": [span("meaning")]},
    ]


def test_valid_cross_linked_source_faithful_corpus() -> None:
    assert validate(corpus()) == []


def test_rejects_wylie_label_as_layer_and_invalid_span_hash() -> None:
    records = copy.deepcopy(corpus())
    records[0]["layer"] = "wylie"
    records[0]["source_spans"][0]["source_sha256"] = "bad"
    errors = validate(records)
    assert any("entry layer" in error for error in errors)
    assert any("lowercase SHA-256" in error for error in errors)


def test_rejects_missing_and_wrong_foreign_keys_and_duplicate_ids() -> None:
    records = copy.deepcopy(corpus())
    records[1]["entry_id"] = "citation:1"
    records[4]["citation_id"] = "citation:missing"
    records[5]["id"] = "entry:1"
    errors = validate(records)
    assert any("is not a entry" in error for error in errors)
    assert any("does not exist" in error for error in errors)
    assert any("duplicate id" in error for error in errors)


def test_print_editorial_variant_requires_structured_not_ocr_kind() -> None:
    records = copy.deepcopy(corpus())
    records[-1]["variant_kind"] = "ocr_damage"
    errors = validate(records)
    assert any("editorial_variant requires" in error for error in errors)
