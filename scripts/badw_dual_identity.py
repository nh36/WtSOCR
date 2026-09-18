#!/usr/bin/env python3
"""Refine BAdW identity evidence without reconciling article text.

Stage C6 consumes the frozen Stage C5 source/candidate evidence and current
QA headword coordinates.  It is intentionally stricter than C5: exact LoC
and Tibetan headings identify a candidate, but a generated-PDF witness is
promoted only when its printed-page evidence resolves that identity too.
Database witnesses remain candidates until a future stage supplies an
independent source discriminator.  No source prose, OCR normalization, or
correction proposal is used here.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable

from wtsocr_entry_segmentation import VOLUMES, anchor_records, read_rows


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_VERSION = "badw-dual-identity-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def local_heading_inventory(qa_root: Path) -> list[dict[str, object]]:
    """Materialize exact local heading fields and their QA provenance."""
    records: list[dict[str, object]] = []
    for volume in VOLUMES:
        records.extend(anchor_records(volume, read_rows(qa_root / volume / f"{volume}_line_zones.tsv")))
    return sorted(records, key=lambda row: str(row["anchor_id"]))


def _validate_sources(sources: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    source_ids = [str(row["source_id"]) for row in sources]
    if source_ids != sorted(source_ids):
        raise ValueError("source snapshot is not ordered by source_id")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("source snapshot has duplicate source_id values")
    return {str(row["source_id"]): row for row in sources}


def _validate_candidates(
    candidates: list[dict[str, object]], source_ids: set[str], local_ids: set[str]
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        source_id = str(candidate["source_id"])
        anchor_id = str(candidate["local_anchor_id"])
        if source_id not in source_ids:
            raise ValueError(f"candidate refers to absent source: {source_id}")
        if anchor_id not in local_ids:
            raise ValueError(f"candidate refers to absent local anchor: {anchor_id}")
        key = (source_id, anchor_id)
        if key in seen:
            raise ValueError(f"duplicate candidate evidence row: {key}")
        seen.add(key)
        grouped[source_id].append(candidate)
    for source_id in grouped:
        grouped[source_id].sort(key=lambda row: (int(row["rank"]), str(row["local_anchor_id"])))
    return grouped


def _candidate_category(candidate: dict[str, object]) -> str:
    latin = bool(candidate["latin_exact"])
    tibetan = bool(candidate["tibetan_exact"])
    page = bool(candidate["printed_page_exact"])
    if latin and tibetan and page:
        return "dual_heading_with_printed_page"
    if latin and tibetan:
        return "dual_heading_without_printed_page"
    if latin or tibetan:
        return "one_field_only"
    if page:
        return "pdf_page_only"
    return "nonexact_candidate"


def assess_source(
    source: dict[str, object], candidates: list[dict[str, object]], headings: dict[str, dict[str, object]]
) -> dict[str, object]:
    """Classify a source while refusing one-field and page-only promotions."""
    delivery = str(source["delivery_type"])
    enriched: list[dict[str, object]] = []
    for candidate in candidates:
        anchor_id = str(candidate["local_anchor_id"])
        heading = headings[anchor_id]
        enriched.append({
            "local_anchor_id": anchor_id,
            "local_coordinate": {
                "volume": heading["volume"], "page": heading["start_page"], "line": heading["start_line"],
            },
            "legacy_entry_ids": candidate["legacy_entry_ids"],
            "rank": candidate["rank"],
            "score": candidate["score"],
            "latin_exact": candidate["latin_exact"],
            "tibetan_exact": candidate["tibetan_exact"],
            "printed_page_exact": candidate["printed_page_exact"],
            "category": _candidate_category(candidate),
            "local_heading_provenance": {
                "parser_status": heading["headword_parser_status"],
                "headword_tibetan": heading["headword_tibetan"],
                "headword_latin_field": heading["headword_latin_field"],
                "headword_loc_display": heading["headword_loc_display"],
            },
        })
    dual = [row for row in enriched if row["latin_exact"] and row["tibetan_exact"]]
    structural_dual = [row for row in dual if row["printed_page_exact"]]
    if not enriched:
        disposition, reason = "unmatched", "no_candidate"
    elif delivery == "generated_pdf_span" and len(structural_dual) == 1:
        disposition, reason = "confident_dual_evidence", "unique_dual_heading_with_printed_page"
    elif len(dual) > 1:
        disposition, reason = "candidate_only", "duplicate_exact_heading"
    elif len(dual) == 1 and delivery == "generated_pdf_span":
        disposition, reason = "candidate_only", "exact_heading_without_printed_page_support"
    elif len(dual) == 1:
        disposition, reason = "candidate_only", "database_requires_independent_source_discriminator"
    elif any(row["latin_exact"] or row["tibetan_exact"] for row in enriched):
        disposition, reason = "candidate_only", "one_field_only"
    elif delivery == "generated_pdf_span" and any(row["printed_page_exact"] for row in enriched):
        disposition, reason = "candidate_only", "pdf_page_only"
    else:
        disposition, reason = "candidate_only", "nonexact_candidate"
    return {
        "contract_version": CONTRACT_VERSION,
        "source_id": source["source_id"],
        "delivery_type": delivery,
        "source_identity": {
            "lemma": source["lemma"], "homonym": source["homonym"], "tibetan": source["tibetan"],
        },
        "disposition": disposition,
        "reason": reason,
        "candidate_count": len(enriched),
        "dual_heading_candidate_count": len(dual),
        "structural_dual_candidate_count": len(structural_dual),
        "candidates": enriched,
    }


def run(source_jsonl: Path, candidate_jsonl: Path, matches_tsv: Path, qa_root: Path, output_root: Path) -> dict[str, object]:
    """Produce deterministic C6 identity assessments entirely offline."""
    sources = _jsonl(source_jsonl)
    source_by_id = _validate_sources(sources)
    headings = local_heading_inventory(qa_root)
    heading_by_id = {str(row["anchor_id"]): row for row in headings}
    if len(headings) != len(heading_by_id):
        raise ValueError("local heading inventory has duplicate anchor IDs")
    candidates = _jsonl(candidate_jsonl)
    candidate_by_source = _validate_candidates(candidates, set(source_by_id), set(heading_by_id))
    # C5's selected-match table is an input provenance check only: C6 never
    # trusts it in preference to the complete candidate evidence.
    with matches_tsv.open(encoding="utf-8", newline="") as handle:
        match_ids = [str(row["source_id"]) for row in csv.DictReader(handle, delimiter="\t")]
    if len(match_ids) != len(sources) or set(match_ids) != set(source_by_id):
        raise ValueError("matches TSV does not contain exactly one row per source")
    assessments = [assess_source(source, candidate_by_source.get(str(source["source_id"]), []), heading_by_id)
                   for source in sources]
    classifications = []
    for assessment in assessments:
        for candidate in assessment["candidates"]:
            classifications.append({
                "contract_version": CONTRACT_VERSION,
                "source_id": assessment["source_id"],
                "delivery_type": assessment["delivery_type"],
                "source_disposition": assessment["disposition"],
                "source_reason": assessment["reason"],
                **candidate,
            })
    output_root.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_root / "local_heading_inventory.jsonl", headings)
    _write_jsonl(output_root / "witness_assessments.jsonl", assessments)
    _write_jsonl(output_root / "candidate_classifications.jsonl", classifications)
    dispositions = Counter(str(row["disposition"]) for row in assessments)
    reasons = Counter(str(row["reason"]) for row in assessments)
    by_delivery: dict[str, dict[str, int]] = {}
    for delivery in sorted({str(row["delivery_type"]) for row in assessments}):
        by_delivery[delivery] = dict(sorted(Counter(
            str(row["disposition"]) for row in assessments if row["delivery_type"] == delivery
        ).items()))
    summary = {
        "contract_version": CONTRACT_VERSION,
        "input_sha256": {
            "source_jsonl": _sha256(source_jsonl), "candidate_jsonl": _sha256(candidate_jsonl),
            "matches_tsv": _sha256(matches_tsv),
        },
        "source_records": len(assessments), "candidate_records": len(candidates),
        "local_heading_records": len(headings),
        "dispositions": dict(sorted(dispositions.items())),
        "reasons": dict(sorted(reasons.items())),
        "dispositions_by_delivery": by_delivery,
        "local_heading_parser_status": dict(sorted(Counter(
            str(row["headword_parser_status"]) for row in headings
        ).items())),
    }
    _write_json(output_root / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-jsonl", required=True, type=Path)
    parser.add_argument("--candidate-jsonl", required=True, type=Path)
    parser.add_argument("--matches-tsv", required=True, type=Path)
    parser.add_argument("--qa-root", default=ROOT / "release/current/qa", type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.source_jsonl, args.candidate_jsonl, args.matches_tsv, args.qa_root, args.output_root),
                     ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
