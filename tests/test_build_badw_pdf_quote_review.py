"""Offline tests for exact-source unresolved-quotation review rows."""
from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_badw_pdf_quote_review import build, review_rows
from extract_badw_pdf_lexical_candidates import extract
from test_build_badw_pdf_nested_candidates import article


def test_review_retains_source_anchor_and_inline_correction() -> None:
    source = article(with_citation=False)
    lexical = extract(source)
    review = review_rows(source, lexical)
    assert len(review) == 1
    row = review[0]
    assert row["reason"] == "no_adjacent_citation"
    assert row["quote_text"] == "„Übersetzung“"
    assert row["citation_text"] == ""
    assert row["review_status"] == "unreviewed"
    assert "printed_correction_nearby" in row["flags"]
    assert row["source_faithful_sha256"] == source["source_faithful_sha256"]
    assert row["quote_visual_start"] == str(source["candidates"]["german_quotes"][0]["visual_start"])
    assert json.loads(row["context_json"])[-1]["text"].endswith("(Quelle 1).")


def test_review_rejects_mismatched_source() -> None:
    source = article(with_citation=False)
    lexical = extract(source)
    lexical["source_faithful_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source identity mismatch"):
        review_rows(source, lexical)


def test_review_rejects_different_cached_source_object() -> None:
    source = article(with_citation=False)
    lexical = extract(source)
    lexical["source_objects"] = [{"sha256": "different"}]
    with pytest.raises(ValueError, match="source identity mismatch"):
        review_rows(source, lexical)


def test_review_queue_is_deterministic_offline(tmp_path: Path) -> None:
    source = article(with_citation=False)
    lexical = extract(source)
    structure_path = tmp_path / "structure.jsonl.gz"
    lexical_path = tmp_path / "lexical.jsonl.gz"
    for path, row in ((structure_path, source), (lexical_path, lexical)):
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    first = tmp_path / "first.tsv"
    second = tmp_path / "second.tsv"
    assert build(structure_path, lexical_path, first) == build(structure_path, lexical_path, second)
    assert first.read_bytes() == second.read_bytes()
    with first.open(encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream, delimiter="\t"))
    assert len(records) == 1
    assert records[0]["quote_text"] == "„Übersetzung“"
