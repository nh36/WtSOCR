from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import badw_identity_handoff as handoff  # noqa: E402


SNAPSHOT = {"contract_version": "badw-source-snapshot-v1", "snapshot_id": "test-snapshot", "verified": True}


def _heading(anchor: str, page: int, line: int) -> dict[str, object]:
    return {"anchor_id": anchor, "volume": "wts_1_34", "start_page": page, "start_line": line}


def _candidate(anchor: str, *, structural: bool = False, rank: int = 1) -> dict[str, object]:
    return {
        "local_anchor_id": anchor, "rank": rank, "score": 0.9,
        "latin_exact": True, "tibetan_exact": True, "printed_page_exact": structural,
        "category": "dual_heading_with_printed_page" if structural else "dual_heading_without_printed_page",
        "legacy_entry_ids": ["17"], "local_coordinate": {"volume": "wts_1_34", "page": 5, "line": 6},
    }


def _assessment(source_id: str, delivery: str, disposition: str, reason: str, candidates: list[dict[str, object]]) -> dict[str, object]:
    return {"source_id": source_id, "delivery_type": delivery, "disposition": disposition,
            "reason": reason, "candidates": candidates}


def test_build_handoff_preserves_candidates_and_only_promotes_strict_edges() -> None:
    assessments = [
        _assessment("source:a", "generated_pdf_span", "confident_dual_evidence", "unique_dual_heading_with_printed_page", [_candidate("a", structural=True), _candidate("b", rank=2)]),
        _assessment("source:b", "generated_pdf_span", "candidate_only", "exact_heading_without_printed_page_support", [_candidate("b")]),
        _assessment("source:c", "database_article", "unmatched", "no_candidate", []),
    ]
    c10 = [{"source_id": "source:b", "c6_disposition": "candidate_only",
            "c6_reason": "exact_heading_without_printed_page_support",
            "disposition": "confident_neighbourhood_evidence",
            "reason": "unique_exact_dual_heading_with_consecutive_two_sided_neighbours",
            "unique_exact_dual_anchor": "b", "neighbourhood": {"two_sided_consecutive": True}}]
    sources, edges, anchors, summary = handoff.build_handoff(
        assessments, c10, [_heading("a", 5, 6), _heading("b", 5, 9)], SNAPSHOT
    )
    assert [row["identity_status"] for row in sources] == ["confident_link", "confident_link", "unmatched"]
    assert [row["identity_method"] for row in sources[:2]] == [
        "unique_exact_dual_heading_with_printed_page",
        "unique_exact_dual_heading_with_two_sided_consecutive_neighbours",
    ]
    assert [(row["source_id"], row["local_anchor_id"], row["edge_disposition"]) for row in edges] == [
        ("source:a", "a", "confident_link"), ("source:a", "b", "candidate_only"),
        ("source:b", "b", "confident_link"),
    ]
    assert anchors[0]["confident_source_ids"] == ["source:a"]
    assert anchors[1]["confident_source_ids"] == ["source:b"]
    assert anchors[1]["candidate_source_ids"] == ["source:a"]
    assert summary["identity_statuses"] == {"confident_link": 2, "unmatched": 1}


def test_handoff_refuses_invalid_neighbourhood_promotion() -> None:
    assessment = _assessment("source:a", "generated_pdf_span", "candidate_only", "exact_heading_without_printed_page_support", [_candidate("a")])
    c10 = [{"source_id": "source:a", "c6_disposition": "candidate_only",
            "c6_reason": "exact_heading_without_printed_page_support",
            "disposition": "confident_neighbourhood_evidence", "reason": "bad",
            "unique_exact_dual_anchor": "a", "neighbourhood": {"two_sided_consecutive": False}}]
    with pytest.raises(ValueError, match="invalid neighbourhood promotion"):
        handoff.build_handoff([assessment], c10, [_heading("a", 5, 6)], SNAPSHOT)


def test_run_is_deterministic_and_verifies_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(handoff, "verify_snapshot", lambda root: SNAPSHOT)
    assessment = _assessment("source:a", "generated_pdf_span", "confident_dual_evidence", "unique_dual_heading_with_printed_page", [_candidate("a", structural=True)])
    c6 = tmp_path / "c6.jsonl"
    c10 = tmp_path / "c10.jsonl"
    headings = tmp_path / "headings.jsonl"
    c6.write_text(json.dumps(assessment) + "\n", encoding="utf-8")
    c10.write_text("", encoding="utf-8")
    headings.write_text(json.dumps(_heading("a", 5, 6)) + "\n", encoding="utf-8")
    snapshot_root = tmp_path / "snapshot"
    snapshot_root.mkdir()
    (snapshot_root / "source_snapshot.json").write_text("{}\n", encoding="utf-8")
    first = tmp_path / "first"
    second = tmp_path / "second"
    handoff.run(snapshot_root, c6, c10, headings, first)
    handoff.run(snapshot_root, c6, c10, headings, second)
    for name in ("source_identity_handoff.jsonl", "candidate_identity_edges.jsonl", "local_anchor_handoff.jsonl", "identity_handoff_manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
