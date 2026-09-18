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


def record(record_type: str, identifier: str, **fields: object) -> dict[str, object]:
    return {
        "contract_version": CONTRACT_VERSION,
        "record_type": record_type,
        "id": identifier,
        "source_snapshot_id": "badw-html:test-snapshot",
        "extraction_run_id": "badw-html-extractor:test-run",
        "source_spans": [span(record_type)],
        **fields,
    }


def corpus() -> list[dict[str, object]]:
    return [
        record("entry", "entry:1", layer="print_faithful", headword={"loc": "ka", "tibetan": "ཀ"}, witness_ids=["badw:article:example"]),
        record("sense", "sense:1", entry_id="entry:1", ordinal=1, definition="Bedeutung"),
        record("bibliographic_source", "bib:1", canonical_label="Example source"),
        record("citation", "citation:1", entry_id="entry:1", raw_text="Ex 1.1", siglum="Ex", authority_status="resolved", bibliographic_source_id="bib:1", locator="1.1"),
        record("attestation", "attestation:1", entry_id="entry:1", sense_id="sense:1", association_status="explicit", ordinal=1, tibetan="ཀ", german_translation="eins", citation_ids=["citation:1"]),
        record("cross_reference", "crossref:1", entry_id="entry:1", marker="↑", resolution_status="resolved", target_url="https://wts-digital.badw.de/lemma/kha/1", target_label="kha"),
        record("editorial_variant", "variant:1", entry_id="entry:1", field_path="senses[0].definition", base_reading="Bedeutung", variant_reading="Neue Bedeutung", variant_kind="post_print_editorial_revision", print_check_status="differs_from_badw"),
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
    records[4]["citation_ids"] = ["citation:missing"]
    records[6]["id"] = "entry:1"
    errors = validate(records)
    assert any("is not a entry" in error for error in errors)
    assert any("does not exist" in error for error in errors)
    assert any("duplicate id" in error for error in errors)


def test_print_editorial_variant_requires_structured_not_ocr_kind() -> None:
    records = copy.deepcopy(corpus())
    records[-1]["variant_kind"] = "ocr_damage"
    errors = validate(records)
    assert any("editorial_variant requires" in error for error in errors)


def test_preserves_unresolved_entry_level_source_citation_without_inventing_authority() -> None:
    records = corpus()
    records[3]["authority_status"] = "unresolved"
    del records[3]["bibliographic_source_id"]
    records[4]["association_status"] = "entry_level"
    del records[4]["sense_id"]
    assert validate(records) == []
