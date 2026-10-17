import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/build_badw_completeness_ledger.py"
SPEC = importlib.util.spec_from_file_location("badw_completeness_ledger", MODULE_PATH)
ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger)


def _write_jsonl_gz(path, records):
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _fixture(tmp_path, *, pending_literal="é", source_text="ཀéx"):
    identity = "fixture:html:one"
    digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    entries = tmp_path / "entries.tsv"
    fields = ["identity", "source_kind", "text_sha256", "characters", "alphabetic_characters",
              "unassigned_characters", "unassigned_alphabetic", "nodes"]
    with entries.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerow(dict(identity=identity, source_kind="html", text_sha256=digest,
                             characters=len(source_text), alphabetic_characters=3,
                             unassigned_characters=1, unassigned_alphabetic=1, nodes=4))
    header = tmp_path / "header.jsonl.gz"
    _write_jsonl_gz(header, [{"identity": identity, "source_kind": "html", "source_sha256": digest,
                              "gaps": [{"start": 1, "end": 2, "family": "unparsed_lexical_prose_pending_review",
                                        "alphabetic_characters": 1}], "source_candidates": []}])
    pending = tmp_path / "pending.jsonl.gz"
    _write_jsonl_gz(pending, [{"identity": identity, "source_kind": "html", "source_sha256": digest,
                               "start": 1, "end": 2, "literal": pending_literal, "family": "lexical_prose_without_proven_boundary",
                               "alphabetic_characters": 1, "source_grammar_family": "bounded_fixture",
                               "unresolved_reason": "No role boundary established.", "context": source_text}])
    accounting = tmp_path / "accounting.json"
    accounting.write_text(json.dumps({"alphabetic_characters": [
        {"family": "source_structural_label", "count": 0},
        {"family": "source_decoding_residue", "count": 0},
    ]}), encoding="utf-8")
    projection = tmp_path / "projections.jsonl"
    record = {"packet": {"identity": identity, "source_kind": "html", "review_text": source_text,
                          "review_text_sha256": digest},
              "projection": {"identity": identity, "review_text_sha256": digest,
                             "contract_version": "fixture-v1"},
              "entry": {"id": identity}, "reader": {"headword": {"display": "fixture"}},
              "metrics": {"identity": identity, "source_kind": "html", "text_sha256": digest}}
    projection.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"baseline_commit": "test", "semantic_store_sha256": "test"}), encoding="utf-8")
    return identity, entries, accounting, header, pending, projection, manifest


def _build(tmp_path, fixture, *, enforce=False):
    identity, entries, accounting, header, pending, projection, manifest = fixture
    db = tmp_path / "ledger.sqlite"
    result = ledger.build_ledger(entries_path=entries, header_json_path=accounting, header_jsonl_path=header,
                                 pending_path=pending, projection_path=projection, manifest_path=manifest,
                                 database_path=db, enforce_certified_totals=enforce)
    return identity, db, result


def test_join_and_query_returns_exact_unicode_span_and_reason(tmp_path):
    fixture = _fixture(tmp_path)
    identity, db, report = _build(tmp_path, fixture)
    result = ledger.query_witness(db, identity)
    assert report["witnesses"] == 1
    assert result["source_sha256"] == hashlib.sha256("ཀéx".encode()).hexdigest()
    assert result["projection_status"] == "projected"
    assert result["meaningful_spans"][0]["literal"] == "é"
    assert result["meaningful_spans"][0]["start"] == 1
    assert result["meaningful_spans"][0]["unresolved_reason"] == "No role boundary established."


def test_rejects_pending_literal_that_disagrees_with_unicode_offsets(tmp_path):
    fixture = _fixture(tmp_path, pending_literal="x")
    with pytest.raises(ledger.LedgerError, match="literal does not match"):
        _build(tmp_path, fixture)


def test_rejects_projection_source_hash_mismatch(tmp_path):
    fixture = list(_fixture(tmp_path))
    projection_path = fixture[5]
    record = json.loads(projection_path.read_text(encoding="utf-8"))
    record["packet"]["review_text_sha256"] = "0" * 64
    projection_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="cached source text hash mismatch"):
        _build(tmp_path, tuple(fixture))


def test_rejects_overlapping_accounting_intervals(tmp_path):
    fixture = list(_fixture(tmp_path))
    identity, _, _, header, *_ = fixture
    _write_jsonl_gz(header, [{"identity": identity, "source_kind": "html",
                              "source_sha256": hashlib.sha256("ཀéx".encode()).hexdigest(),
                              "gaps": [{"start": 0, "end": 2, "family": "a", "alphabetic_characters": 2},
                                       {"start": 1, "end": 2, "family": "b", "alphabetic_characters": 1}],
                              "source_candidates": []}])
    with pytest.raises(ledger.LedgerError, match="overlapping accounting intervals"):
        _build(tmp_path, tuple(fixture))


def test_rejects_duplicate_entry_identity(tmp_path):
    fixture = list(_fixture(tmp_path))
    entries = fixture[1]
    original = entries.read_text(encoding="utf-8")
    entries.write_text(original + original.splitlines()[1] + "\n", encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="duplicate identity"):
        _build(tmp_path, tuple(fixture))


def test_semantic_store_joins_by_identity_and_rejects_source_hash_mismatch(tmp_path):
    fixture = _fixture(tmp_path)
    identity, entries, accounting, header, pending, projection, manifest = fixture
    semantic = tmp_path / "semantic.tsv"
    digest = hashlib.sha256("ཀéx".encode()).hexdigest()
    fields = ["identity", "source_kind", "text_sha256", "citations", "owned_citations"]
    with semantic.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerow({"identity": identity, "source_kind": "html", "text_sha256": digest,
                         "citations": 2, "owned_citations": 1})
    db = tmp_path / "ledger.sqlite"
    ledger.build_ledger(entries_path=entries, header_json_path=accounting, header_jsonl_path=header,
                        pending_path=pending, projection_path=projection, manifest_path=manifest,
                        database_path=db, semantic_entries_path=semantic, enforce_certified_totals=False)
    result = ledger.query_witness(db, identity)
    assert result["semantic_statistics"] == {"citations": 2, "owned_citations": 1}

    semantic.write_text(semantic.read_text().replace(digest, "0" * 64), encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="semantic-store source kind/hash mismatch"):
        ledger.build_ledger(entries_path=entries, header_json_path=accounting, header_jsonl_path=header,
                            pending_path=pending, projection_path=projection, manifest_path=manifest,
                            database_path=db, semantic_entries_path=semantic, enforce_certified_totals=False)
