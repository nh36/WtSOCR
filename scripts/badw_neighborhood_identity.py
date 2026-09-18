#!/usr/bin/env python3
"""Add conservative PDF-heading neighbourhood evidence to BAdW identity work.

This is still source identity work, not article reconciliation.  It consumes a
frozen source snapshot and the C6 dual-heading assessments.  A generated-PDF
heading can gain a *neighbourhood-confident* identity only when it and both
immediate PDF-page neighbours each have one exact LoC-and-Tibetan candidate,
and those three candidates are consecutive local coordinate anchors.  Thus a
single repeated headword, one-field match, page match, or prose resemblance
cannot promote an association.

The WTS transliteration is historical Library of Congress (LoC), not Wylie.
No source text is compared or copied into this output.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_VERSION = "badw-neighborhood-identity-v1"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _unique_dual_anchor(assessment: dict[str, Any]) -> str | None:
    """Return one exact dual-heading anchor, refusing duplicate identities."""
    anchors = {
        str(candidate["local_anchor_id"])
        for candidate in assessment.get("candidates", [])
        if bool(candidate.get("latin_exact")) and bool(candidate.get("tibetan_exact"))
    }
    return next(iter(anchors)) if len(anchors) == 1 else None


def _source_pages(sources: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    pages: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in sources:
        if source.get("delivery_type") != "generated_pdf_span":
            continue
        provenance = source.get("provenance", {})
        page_id = provenance.get("page_id")
        run_start = provenance.get("run_start")
        if not isinstance(page_id, str) or not isinstance(run_start, int):
            continue
        pages[page_id].append(source)
    for records in pages.values():
        records.sort(key=lambda record: (int(record["provenance"]["run_start"]), str(record["source_id"])))
    return pages


def _local_neighbours(headings: Iterable[dict[str, Any]]) -> dict[str, dict[str, str | None]]:
    by_volume: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for heading in headings:
        by_volume[str(heading["volume"])].append(heading)
    result: dict[str, dict[str, str | None]] = {}
    for records in by_volume.values():
        records.sort(key=lambda row: (int(row["start_page"]), int(row["start_line"]), str(row["anchor_id"])))
        for index, record in enumerate(records):
            result[str(record["anchor_id"])] = {
                "previous": str(records[index - 1]["anchor_id"]) if index else None,
                "next": str(records[index + 1]["anchor_id"]) if index + 1 < len(records) else None,
            }
    return result


def assess(
    sources: list[dict[str, Any]], assessments: list[dict[str, Any]], headings: list[dict[str, Any]]
) -> list[dict[str, object]]:
    """Return deterministic C10 assessments without altering C6 evidence."""
    source_by_id = {str(row["source_id"]): row for row in sources}
    assessment_by_id = {str(row["source_id"]): row for row in assessments}
    if set(source_by_id) != set(assessment_by_id):
        raise ValueError("source snapshot and C6 assessments do not contain the same source IDs")
    if len(source_by_id) != len(sources) or len(assessment_by_id) != len(assessments):
        raise ValueError("source snapshot or C6 assessments contain duplicate source IDs")
    local = _local_neighbours(headings)
    pages = _source_pages(sources)
    result: list[dict[str, object]] = []
    for page_id in sorted(pages):
        page_sources = pages[page_id]
        for index, source in enumerate(page_sources):
            current = assessment_by_id[str(source["source_id"])]
            target = _unique_dual_anchor(current)
            previous_source = page_sources[index - 1] if index else None
            next_source = page_sources[index + 1] if index + 1 < len(page_sources) else None
            previous_anchor = (_unique_dual_anchor(assessment_by_id[str(previous_source["source_id"])])
                               if previous_source is not None else None)
            next_anchor = (_unique_dual_anchor(assessment_by_id[str(next_source["source_id"])])
                           if next_source is not None else None)
            expected = local.get(target, {}) if target else {}
            previous_matches = bool(target and previous_anchor and previous_anchor == expected.get("previous"))
            next_matches = bool(target and next_anchor and next_anchor == expected.get("next"))
            two_sided = previous_matches and next_matches
            c6_disposition = str(current["disposition"])
            c6_reason = str(current["reason"])
            if two_sided and c6_disposition == "candidate_only":
                disposition = "confident_neighbourhood_evidence"
                reason = "unique_exact_dual_heading_with_consecutive_two_sided_neighbours"
            elif previous_matches or next_matches:
                disposition = c6_disposition
                reason = "one_sided_neighbourhood_support_not_promoted"
            else:
                disposition = c6_disposition
                reason = c6_reason
            result.append({
                "contract_version": CONTRACT_VERSION,
                "source_id": source["source_id"],
                "delivery_type": source["delivery_type"],
                "c6_disposition": c6_disposition,
                "c6_reason": c6_reason,
                "disposition": disposition,
                "reason": reason,
                "page_id": page_id,
                "run_start": source["provenance"]["run_start"],
                "unique_exact_dual_anchor": target,
                "neighbourhood": {
                    "previous_source_id": previous_source["source_id"] if previous_source else None,
                    "previous_unique_exact_dual_anchor": previous_anchor,
                    "expected_previous_anchor": expected.get("previous"),
                    "previous_matches": previous_matches,
                    "next_source_id": next_source["source_id"] if next_source else None,
                    "next_unique_exact_dual_anchor": next_anchor,
                    "expected_next_anchor": expected.get("next"),
                    "next_matches": next_matches,
                    "two_sided_consecutive": two_sided,
                },
            })
    result.sort(key=lambda row: str(row["source_id"]))
    return result


def run(source_jsonl: Path, c6_assessments_jsonl: Path, headings_jsonl: Path, output_root: Path) -> dict[str, object]:
    sources = _jsonl(source_jsonl)
    assessments = _jsonl(c6_assessments_jsonl)
    headings = _jsonl(headings_jsonl)
    records = assess(sources, assessments, headings)
    output_root.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_root / "neighbourhood_assessments.jsonl", records)
    summary = {
        "contract_version": CONTRACT_VERSION,
        "input_sha256": {
            "source_jsonl": _sha256(source_jsonl),
            "c6_assessments_jsonl": _sha256(c6_assessments_jsonl),
            "headings_jsonl": _sha256(headings_jsonl),
        },
        "pdf_span_sources": len(records),
        "dispositions": dict(sorted(Counter(str(row["disposition"]) for row in records).items())),
        "reasons": dict(sorted(Counter(str(row["reason"]) for row in records).items())),
        "two_sided_consecutive_neighbourhoods": sum(
            bool(row["neighbourhood"]["two_sided_consecutive"]) for row in records
        ),
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-jsonl", required=True, type=Path)
    parser.add_argument("--c6-assessments-jsonl", required=True, type=Path)
    parser.add_argument("--headings-jsonl", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(**vars(args)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
