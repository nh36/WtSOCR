#!/usr/bin/env python3
"""Materialize a snapshot-bound BAdW-to-local identity handoff.

This is deliberately an identity-only boundary between the ignored BAdW
source corpus and later lexical/reconciliation work.  It verifies the
immutable source snapshot first, preserves every C6 candidate edge, and lets
only the existing C6/C10 strict gates create provisional local links.  It
does not compare article prose, normalize readings, or generate corrections.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

from badw_source_snapshot import verify_snapshot


CONTRACT_VERSION = "badw-identity-handoff-v1"
CONFIDENT_DISPOSITIONS = {"confident_dual_evidence", "confident_neighbourhood_evidence"}


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _validate_unique(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    ids = [str(row[key]) for row in rows]
    if ids != sorted(ids):
        raise ValueError(f"{label} is not ordered by {key}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} has duplicate {key} values")
    return dict(zip(ids, rows))


def _candidate_edges(assessment: dict[str, Any]) -> list[dict[str, object]]:
    source_id = str(assessment["source_id"])
    result = []
    for candidate in assessment.get("candidates", []):
        result.append({
            "contract_version": CONTRACT_VERSION,
            "source_id": source_id,
            "local_anchor_id": candidate["local_anchor_id"],
            "rank": candidate["rank"],
            "score": candidate["score"],
            "category": candidate["category"],
            "latin_exact": candidate["latin_exact"],
            "tibetan_exact": candidate["tibetan_exact"],
            "printed_page_exact": candidate["printed_page_exact"],
            "legacy_entry_ids": candidate["legacy_entry_ids"],
            "local_coordinate": candidate["local_coordinate"],
        })
    seen = [str(row["local_anchor_id"]) for row in result]
    if len(seen) != len(set(seen)):
        raise ValueError(f"duplicate candidate anchors for {source_id}")
    return sorted(result, key=lambda row: (int(row["rank"]), str(row["local_anchor_id"])))


def _select_confident_anchor(assessment: dict[str, Any], c10: dict[str, Any] | None) -> tuple[str | None, str | None]:
    disposition = str(c10["disposition"]) if c10 else str(assessment["disposition"])
    if disposition not in CONFIDENT_DISPOSITIONS:
        return None, None
    if disposition == "confident_neighbourhood_evidence":
        if not c10 or not bool(c10["neighbourhood"]["two_sided_consecutive"]):
            raise ValueError(f"invalid neighbourhood promotion for {assessment['source_id']}")
        anchor = c10.get("unique_exact_dual_anchor")
        method = "unique_exact_dual_heading_with_two_sided_consecutive_neighbours"
    else:
        structural = [candidate for candidate in assessment.get("candidates", [])
                      if candidate["category"] == "dual_heading_with_printed_page"]
        if len(structural) != 1:
            raise ValueError(f"invalid dual-evidence promotion for {assessment['source_id']}")
        anchor = structural[0]["local_anchor_id"]
        method = "unique_exact_dual_heading_with_printed_page"
    if not isinstance(anchor, str):
        raise ValueError(f"confident source without local anchor: {assessment['source_id']}")
    return anchor, method


def build_handoff(assessments: list[dict[str, Any]], neighbourhoods: list[dict[str, Any]],
                  headings: list[dict[str, Any]], snapshot: dict[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """Build deterministic records after the caller has verified the snapshot."""
    assessment_by_id = _validate_unique(assessments, "source_id", "C6 assessments")
    heading_by_id = _validate_unique(headings, "anchor_id", "local heading inventory")
    c10_by_id = _validate_unique(neighbourhoods, "source_id", "C10 assessments")
    if not set(c10_by_id).issubset(assessment_by_id):
        raise ValueError("C10 assessment refers to absent C6 source")

    source_rows: list[dict[str, object]] = []
    edge_rows: list[dict[str, object]] = []
    linked_by_anchor: dict[str, list[str]] = defaultdict(list)
    candidate_by_anchor: dict[str, list[str]] = defaultdict(list)
    for source_id, assessment in assessment_by_id.items():
        c10 = c10_by_id.get(source_id)
        if c10 and (c10["c6_disposition"] != assessment["disposition"] or c10["c6_reason"] != assessment["reason"]):
            raise ValueError(f"C10/C6 disagreement for {source_id}")
        final_disposition = str(c10["disposition"]) if c10 else str(assessment["disposition"])
        final_reason = str(c10["reason"]) if c10 else str(assessment["reason"])
        selected_anchor, method = _select_confident_anchor(assessment, c10)
        if selected_anchor is not None and selected_anchor not in heading_by_id:
            raise ValueError(f"confident source references absent anchor: {source_id}")
        edges = _candidate_edges(assessment)
        for edge in edges:
            anchor = str(edge["local_anchor_id"])
            if anchor not in heading_by_id:
                raise ValueError(f"candidate source references absent anchor: {source_id}")
            edge["edge_disposition"] = "confident_link" if anchor == selected_anchor else "candidate_only"
            edge_rows.append(edge)
            (linked_by_anchor if anchor == selected_anchor else candidate_by_anchor)[anchor].append(source_id)
        identity_status = "confident_link" if selected_anchor else ("unmatched" if final_disposition == "unmatched" else "candidate_only")
        source_rows.append({
            "contract_version": CONTRACT_VERSION,
            "source_snapshot_id": snapshot["snapshot_id"],
            "source_id": source_id,
            "delivery_type": assessment["delivery_type"],
            "identity_status": identity_status,
            "evidence_disposition": final_disposition,
            "evidence_reason": final_reason,
            "identity_method": method,
            "linked_local_anchor_id": selected_anchor,
            "candidate_count": len(edges),
        })
    anchor_rows = []
    for anchor_id in sorted(heading_by_id):
        heading = heading_by_id[anchor_id]
        anchor_rows.append({
            "contract_version": CONTRACT_VERSION,
            "source_snapshot_id": snapshot["snapshot_id"],
            "local_anchor_id": anchor_id,
            "local_coordinate": {"volume": heading["volume"], "page": heading["start_page"], "line": heading["start_line"]},
            "identity_kind": "provisional_local_anchor",
            "confident_source_ids": sorted(linked_by_anchor[anchor_id]),
            "candidate_source_ids": sorted(candidate_by_anchor[anchor_id]),
        })
    source_rows.sort(key=lambda row: str(row["source_id"]))
    edge_rows.sort(key=lambda row: (str(row["source_id"]), int(row["rank"]), str(row["local_anchor_id"])))
    summary = {
        "contract_version": CONTRACT_VERSION,
        "source_snapshot_id": snapshot["snapshot_id"],
        "source_records": len(source_rows), "candidate_edges": len(edge_rows), "local_anchors": len(anchor_rows),
        "identity_statuses": dict(sorted(Counter(str(row["identity_status"]) for row in source_rows).items())),
        "confident_methods": dict(sorted(Counter(str(row["identity_method"]) for row in source_rows if row["identity_method"]).items())),
    }
    return source_rows, edge_rows, anchor_rows, summary


def run(snapshot_root: Path, c6_assessments: Path, c10_assessments: Path, headings: Path, output_root: Path) -> dict[str, object]:
    """Verify the snapshot and write a reproducible, identity-only handoff."""
    snapshot = verify_snapshot(snapshot_root)
    source_rows, edge_rows, anchor_rows, summary = build_handoff(
        _jsonl(c6_assessments), _jsonl(c10_assessments), _jsonl(headings), snapshot
    )
    output_root.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_root / "source_identity_handoff.jsonl", source_rows)
    _write_jsonl(output_root / "candidate_identity_edges.jsonl", edge_rows)
    _write_jsonl(output_root / "local_anchor_handoff.jsonl", anchor_rows)
    summary["inputs"] = {
        "source_snapshot": {"path": str(snapshot_root), "sha256": _sha(snapshot_root / "source_snapshot.json")},
        "c6_assessments": {"path": str(c6_assessments), "sha256": _sha(c6_assessments)},
        "c10_assessments": {"path": str(c10_assessments), "sha256": _sha(c10_assessments)},
        "local_headings": {"path": str(headings), "sha256": _sha(headings)},
    }
    summary["outputs"] = {name: _sha(output_root / name) for name in (
        "source_identity_handoff.jsonl", "candidate_identity_edges.jsonl", "local_anchor_handoff.jsonl")}
    (output_root / "identity_handoff_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", required=True, type=Path)
    parser.add_argument("--c6-assessments", required=True, type=Path)
    parser.add_argument("--c10-assessments", required=True, type=Path)
    parser.add_argument("--headings", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(**vars(args)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
