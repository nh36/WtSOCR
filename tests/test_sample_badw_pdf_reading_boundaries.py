"""Sampling deduplicates nested candidate boundaries reproducibly."""
from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from derive_badw_pdf_reading import VERSION
from sample_badw_pdf_reading_boundaries import boundary_rows, sample


def fixture(tmp_path: Path) -> Path:
    row = {"contract_version": VERSION, "article_id": "article-1", "visual_sha256": "a" * 64,
           "annotations": {"definitions": [], "belegstellen": [], "translations": []}}
    item = {"source_text": "für\nskt.", "source_visual_start": 10,
            "boundaries": [{"source_local_offset": 3, "source_visual_offset": 13,
                            "kind": "same_item_space", "replacement": " "}]}
    row["annotations"]["definitions"].append(item)
    row["annotations"]["belegstellen"].append(item)
    path = tmp_path / "readings.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def test_unique_visual_boundary_and_deterministic_sample(tmp_path: Path) -> None:
    source = fixture(tmp_path)
    boundaries, counts = boundary_rows(source)
    assert len(boundaries) == 1
    assert counts["duplicate_candidate_occurrences"] == 1
    first = tmp_path / "first.tsv"
    second = tmp_path / "second.tsv"
    assert sample(source, first) == sample(source, second)
    assert first.read_bytes() == second.read_bytes()
    with first.open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream, delimiter="\t"))
    assert row["left_context"] == "für"
    assert row["right_context"] == "skt."
    assert row["proposed_replacement"] == " "


def test_conflicting_duplicate_boundary_is_rejected(tmp_path: Path) -> None:
    source = fixture(tmp_path)
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        row = json.loads(stream.readline())
    row["annotations"]["belegstellen"][0] = json.loads(json.dumps(row["annotations"]["definitions"][0]))
    row["annotations"]["belegstellen"][0]["boundaries"][0]["replacement"] = "\n"
    with gzip.open(source, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    with pytest.raises(ValueError, match="inconsistent duplicate"):
        boundary_rows(source)
