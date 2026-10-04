#!/usr/bin/env python3
"""Extract lossless OCR candidates from hash-pinned, scan-reviewed bibliography ranges.

This is NOT an authority importer. Two-up OCR ordering, inherited authors and
every candidate boundary require later print review. Unclassified text is kept.
Offsets are zero-based Python Unicode offsets into the exact OCR source file.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re

from badw_bibliography import digest, dumps, file_digest, write_jsonl

VERSION = "print-bibliography-candidates-v1"
PAGE = re.compile(r"^=== page (\d+) ===\r?\n", re.M)
AUTHOR_YEAR = re.compile(r"^[A-ZÄÖÜ][^\n\r]*?\b(?:1[5-9]|20)\d{2}[a-z]?\s*:", re.M)
INHERITED_YEAR = re.compile(r"^[ \t]*(?:1[5-9]|20)\d{2}[a-z]?\s*:", re.M)


def extract(pdf: Path, ocr: Path, review: dict) -> tuple[list[dict], list[dict]]:
    if file_digest(pdf) != review["pdf_sha256"] or file_digest(ocr) != review["ocr_sha256"]:
        raise ValueError("stale print range: PDF/OCR hash mismatch")
    start_page, end_page = int(review["start_page"]), int(review["end_page"])
    if start_page <= 0 or end_page < start_page or not review["evidence_note"].strip():
        raise ValueError("invalid print range or missing review evidence")
    text = ocr.read_bytes().decode("utf-8", errors="strict")
    headers = list(PAGE.finditer(text))
    if len({int(h[1]) for h in headers}) != len(headers):
        raise ValueError("duplicate OCR scan page")
    boundaries = {int(h[1]): (h.end(), headers[i+1].start() if i+1 < len(headers) else len(text))
                  for i, h in enumerate(headers)}
    if any(p not in boundaries for p in range(start_page, end_page+1)):
        raise ValueError("missing OCR scan page")
    def heading(page, value):
        a, b = boundaries[page]
        hits = list(re.finditer(r"(?m)^" + re.escape(value) + r"\r?$", text[a:b]))
        if len(hits) != 1:
            raise ValueError("missing or ambiguous range heading")
        return a + hits[0].start(), a + hits[0].end()
    _, left = heading(start_page, review["start_heading"])
    right, _ = heading(end_page, review["end_heading"])
    if right <= left:
        raise ValueError("reversed print headings")
    provenance = {k: review[k] for k in ("range_id", "source_label", "pdf_sha256", "ocr_sha256", "evidence_note")}
    pages, candidates = [], []
    # Each page's selected text partitions exactly. Do not drop preambles,
    # running headers, or residuals, or normalize hyphenation/line breaks.
    for page in range(start_page, end_page+1):
        a, b = boundaries[page]
        begin, end = max(a, left), min(b, right)
        selected = text[begin:end]
        page_id = "print-page-" + digest((review["ocr_sha256"] + ":" + str(page)).encode())[:32]
        pages.append({**provenance, "id": page_id, "scan_page": page,
                      "start": a, "end": b, "raw_text": text[a:b],
                      "selected_start": begin, "selected_end": end,
                      "status": "reviewed_range_unreviewed_ocr"})
        starts = {h.start(): "author_year_candidate" for h in AUTHOR_YEAR.finditer(selected)}
        starts.update({h.start(): "inherited_year_candidate" for h in INHERITED_YEAR.finditer(selected)})
        starts.setdefault(0, "unclassified_span")
        ordered = sorted(starts)
        for i, offset in enumerate(ordered):
            stop = ordered[i+1] if i+1 < len(ordered) else len(selected)
            raw = selected[offset:stop]
            if not raw:
                continue
            absolute = begin+offset
            candidates.append({**provenance, "id": "print-candidate-" + digest(
                (page_id + ":" + str(absolute) + ":" + str(begin+stop)).encode())[:32],
                "page_id": page_id, "scan_page": page, "start": absolute, "end": begin+stop,
                "raw_text": raw, "candidate_type": starts[offset],
                "status": "requires_print_boundary_and_metadata_review",
                "authority_id": None, "preceding_author": None})
    return pages, candidates


def build(registry: Path, ranges: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("use a new output directory; snapshots are immutable")
    if "work" not in output.resolve().parts:
        raise ValueError("generated print material must remain under work/")
    with registry.open(encoding="utf-8", newline="") as stream:
        sources = {r["label"]: r for r in csv.DictReader(stream, delimiter="\t")}
    with ranges.open(encoding="utf-8", newline="") as stream:
        reviews = list(csv.DictReader(stream, delimiter="\t"))
    if len({r["range_id"] for r in reviews}) != len(reviews):
        raise ValueError("duplicate range identity")
    pages, candidates = [], []
    for review in sorted(reviews, key=lambda r: r["range_id"]):
        source = sources[review["source_label"]]
        if source["sha256"] != review["pdf_sha256"]:
            raise ValueError("range disagrees with registered PDF")
        pdf = Path(source["filename"])
        p, c = extract(pdf, pdf.with_suffix(".vision.txt"), review)
        pages.extend(p)
        candidates.extend(c)
    output.mkdir(parents=True)
    write_jsonl(output / "pages.jsonl", pages)
    write_jsonl(output / "candidates.jsonl", candidates)
    summary = {"version": VERSION, "registry_sha256": file_digest(registry),
               "ranges_sha256": file_digest(ranges), "ranges": len(reviews),
               "page_observations": len(pages), "candidates": len(candidates),
               "candidate_types": dict(sorted(Counter(c["candidate_type"] for c in candidates).items())),
               "output_hashes": {p.name: file_digest(p) for p in sorted(output.iterdir())},
               "limitations": ["Not verified bibliography authorities", "Page-level candidates may cross entry boundaries",
                               "Inherited authors are unresolved", "OCR text and two-up reading order require print review"]}
    (output / "manifest.json").write_text(dumps(summary) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("data/source_pdfs.tsv"))
    parser.add_argument("--ranges", type=Path, default=Path("data/bibliography_print_ranges.tsv"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.registry, args.ranges, args.output), ensure_ascii=False, sort_keys=True))
