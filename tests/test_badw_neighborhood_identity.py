from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from badw_neighborhood_identity import run  # noqa: E402


def _jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _source(identifier: str, start: int) -> dict[str, object]:
    return {
        "source_id": identifier, "delivery_type": "generated_pdf_span", "lemma": identifier,
        "homonym": "", "tibetan": "", "source_text": "not used",
        "provenance": {"page_id": "page-1", "run_start": start},
    }


def _assessment(identifier: str, anchors: list[str]) -> dict[str, object]:
    return {
        "source_id": identifier, "disposition": "candidate_only",
        "reason": "exact_heading_without_printed_page_support",
        "candidates": [
            {"local_anchor_id": anchor, "latin_exact": True, "tibetan_exact": True}
            for anchor in anchors
        ],
    }


def test_two_sided_consecutive_exact_headings_promote_without_prose(tmp_path: Path):
    sources = [_source("first", 10), _source("middle", 20), _source("last", 30)]
    assessments = [_assessment("first", ["v:1:1"]), _assessment("middle", ["v:1:2"]), _assessment("last", ["v:1:3"])]
    headings = [
        {"anchor_id": "v:1:1", "volume": "v", "start_page": 1, "start_line": 1},
        {"anchor_id": "v:1:2", "volume": "v", "start_page": 1, "start_line": 2},
        {"anchor_id": "v:1:3", "volume": "v", "start_page": 1, "start_line": 3},
    ]
    paths = [tmp_path / name for name in ("sources.jsonl", "assessments.jsonl", "headings.jsonl")]
    for path, rows in zip(paths, (sources, assessments, headings)):
        _jsonl(path, rows)
    summary = run(*paths, tmp_path / "out")
    rows = {row["source_id"]: row for row in (
        json.loads(line) for line in (tmp_path / "out/neighbourhood_assessments.jsonl").read_text(encoding="utf-8").splitlines()
    )}
    assert rows["middle"]["disposition"] == "confident_neighbourhood_evidence"
    assert rows["middle"]["neighbourhood"]["two_sided_consecutive"] is True
    assert rows["first"]["disposition"] == "candidate_only"
    assert summary["dispositions"] == {"candidate_only": 2, "confident_neighbourhood_evidence": 1}


def test_one_sided_and_duplicate_headings_never_promote_and_output_is_deterministic(tmp_path: Path):
    sources = [_source("first", 10), _source("middle", 20), _source("last", 30)]
    assessments = [_assessment("first", ["v:1:1"]), _assessment("middle", ["v:1:2", "v:2:2"]), _assessment("last", ["v:1:3"])]
    headings = [
        {"anchor_id": "v:1:1", "volume": "v", "start_page": 1, "start_line": 1},
        {"anchor_id": "v:1:2", "volume": "v", "start_page": 1, "start_line": 2},
        {"anchor_id": "v:1:3", "volume": "v", "start_page": 1, "start_line": 3},
        {"anchor_id": "v:2:2", "volume": "v", "start_page": 2, "start_line": 2},
    ]
    paths = [tmp_path / name for name in ("sources.jsonl", "assessments.jsonl", "headings.jsonl")]
    for path, rows in zip(paths, (sources, assessments, headings)):
        _jsonl(path, rows)
    run(*paths, tmp_path / "one")
    run(*paths, tmp_path / "two")
    assert (tmp_path / "one/neighbourhood_assessments.jsonl").read_bytes() == (tmp_path / "two/neighbourhood_assessments.jsonl").read_bytes()
    rows = {row["source_id"]: row for row in (
        json.loads(line) for line in (tmp_path / "one/neighbourhood_assessments.jsonl").read_text(encoding="utf-8").splitlines()
    )}
    assert rows["middle"]["disposition"] == "candidate_only"
    assert rows["middle"]["unique_exact_dual_anchor"] is None
