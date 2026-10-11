#!/usr/bin/env python3
"""Extract lossless OCR candidates from hash-pinned, scan-reviewed bibliography ranges.

Extraction does not create authorities. Only separate, explicit visual reviews
can import publication identities or explicit online crosswalks. Two-up OCR ordering, inherited
authors and candidate boundaries require review. Unclassified text is kept.
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
PUBLICATION_YEAR = r"(?:1[5-9]|20)\d{2}[a-z]?(?:[-–](?:\d{2}|\d{4})[a-z]?)?"
AUTHOR_YEAR = re.compile(r"^[A-ZÄÖÜ][^\n\r]*?\b" + PUBLICATION_YEAR + r"\s*[:.]", re.M)
INHERITED_YEAR = re.compile(r"^[ \t]*" + PUBLICATION_YEAR + r"\s*[:.]", re.M)


def reviewed_apparatus_occurrences(records: Path, registry: Path, zones: Path,
                                  online_rows: list[dict]) -> list[dict]:
    """Import explicit facsimile readings with independently checked OCR spans.

    Each span is confined to one scan page; a record can have several spans,
    including across pages. Identity is supplied by review, never inferred from
    normalized wording. Transcription is deliberately separate from raw OCR.
    """
    with registry.open(encoding="utf-8", newline="") as stream:
        sources = {r["label"]: r for r in csv.DictReader(stream, delimiter="\t")}
    with zones.open(encoding="utf-8", newline="") as stream:
        inventory = {r["zone_id"]: r for r in csv.DictReader(stream, delimiter="\t")}
    online = {r["occurrence_id"]: r for r in online_rows}
    readings = [json.loads(line) for line in records.read_text(encoding="utf-8").splitlines()]
    if len({r["id"] for r in readings}) != len(readings):
        raise ValueError("duplicate apparatus occurrence")
    by_id = {r["id"]: r for r in readings}
    verified, imported = {}, []
    review_sha = file_digest(records)
    for reading in readings:
        zone = inventory[reading["zone_id"]]
        label = reading["source_label"]
        if (zone["source_label"] != label or zone["pdf_sha256"] != reading["pdf_sha256"]
                or zone["ocr_sha256"] != reading["ocr_sha256"]
                or sources[label]["sha256"] != reading["pdf_sha256"]):
            raise ValueError("stale apparatus zone/source")
        if label not in verified:
            pdf = Path(sources[label]["filename"])
            ocr = pdf.with_suffix(".vision.txt")
            if file_digest(pdf) != reading["pdf_sha256"]:
                raise ValueError("stale apparatus PDF")
            text = ocr.read_bytes().decode("utf-8")
            headers = list(PAGE.finditer(text))
            bounds = {int(h[1]): (h.end(), headers[i+1].start() if i+1 < len(headers) else len(text))
                      for i, h in enumerate(headers)}
            verified[label] = (file_digest(ocr), text, bounds)
        ocr_sha, text, bounds = verified[label]
        if ocr_sha != reading["ocr_sha256"]:
            raise ValueError("stale apparatus OCR")
        spans = reading["source_spans"]
        if not spans or not reading["facsimile_spans"]:
            raise ValueError("missing apparatus provenance")
        for span in spans:
            page = span["scan_page"]
            a, b = bounds.get(page, (-1, -1))
            if not (int(zone["start_scan_page"]) <= page <= int(zone["end_scan_page"])
                    and a <= span["start"] < span["end"] <= b
                    and text[span["start"]:span["end"]] == span["raw_text"]):
                raise ValueError("invalid apparatus OCR span")
        facsimile_pages = set()
        for span in reading["facsimile_spans"]:
            x0, y0, x1, y1 = span["bbox_fraction"]
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
                    and int(zone["start_scan_page"]) <= span["scan_page"] <= int(zone["end_scan_page"])):
                raise ValueError("invalid apparatus facsimile span")
            facsimile_pages.add(span["scan_page"])
        if not {s["scan_page"] for s in spans} <= facsimile_pages:
            raise ValueError("OCR span lacks facsimile provenance")
        transcription_only = reading["status"] == "visually_reviewed_transcription"
        if (reading["status"] not in {"visually_reviewed_identity", "visually_reviewed_transcription"} or not reading["evidence_note"].strip()
                or not reading["verified_transcription"].strip()
                or reading["kind"] not in {"work", "publication", "abbreviation", "editorial"}
                or (reading["kind"] == "editorial" and not transcription_only)):
            raise ValueError("missing reviewed apparatus identity")
        if reading.get("apparatus_role") != "dictionary_source" and not transcription_only:
            raise ValueError("secondary apparatus cannot become a citation authority")
        crosswalk, authority = reading.get("online_crosswalk"), None
        if transcription_only:
            if reading.get("authority_id") is not None or crosswalk:
                raise ValueError("transcription-only occurrence cannot assert authority identity")
        elif crosswalk:
            row = online.get(crosswalk["occurrence_id"])
            if (not row or row["id"] != reading["authority_id"]
                    or crosswalk["authority_id"] != row["id"] or row["kind"] != reading["kind"]
                    or row["source_sha256"] != crosswalk["source_sha256"]
                    or digest(row["text"].encode()) != crosswalk["text_sha256"]
                    or not crosswalk["evidence"].strip()):
                raise ValueError("stale apparatus online crosswalk")
        else:
            if not reading["authority_id"].startswith(reading["kind"] + "-print-"):
                raise ValueError("unreviewed apparatus authority crosswalk")
            authority = {"id": reading["authority_id"], "kind": reading["kind"],
                         "label": reading["label"], "year": reading["year_as_printed"],
                         "scope": "published_print", "status": "reviewed_print_identity"}
        manifestation = reading.get("manifestation_of")
        if manifestation:
            original = by_id.get(manifestation)
            if (not original or original["id"] == reading["id"]
                    or original["authority_id"] != reading["authority_id"]
                    or reading.get("manifestation_relation") != "same_list_different_typesetting"):
                raise ValueError("conflicting manifestation identity")
        imported.append({"id": reading["id"], "authority_id": reading["authority_id"],
                         "online_occurrence_id": crosswalk["occurrence_id"] if crosswalk else None,
                         "authority": authority, "candidate": reading,
                         "verified_transcription": reading["verified_transcription"], "review": reading,
                         "review_sha256": review_sha, "status": reading["status"],
                         "scope": "published_print",
                         "limitations": "Identity review does not establish citation edition compatibility"})
    return imported


def reviewed_occurrences(candidates: Path, reviews: Path, registry: Path,
                         online_rows: list[dict]) -> list[dict]:
    """Import only explicit, hash-pinned visual reviews, not OCR candidates.

    A crosswalk establishes publication identity, never edition compatibility
    for citations. Printed transcription and online wording remain separate.
    Cross-page records require a later multi-span review contract.
    """
    candidate_rows = [json.loads(line) for line in candidates.read_text(encoding="utf-8").splitlines()]
    by_id = {r["id"]: r for r in candidate_rows}
    if len(by_id) != len(candidate_rows):
        raise ValueError("duplicate print candidate identity")
    with registry.open(encoding="utf-8", newline="") as stream:
        sources = {r["label"]: r for r in csv.DictReader(stream, delimiter="\t")}
    online = {r["occurrence_id"]: r for r in online_rows}
    with reviews.open(encoding="utf-8", newline="") as stream:
        review_rows = list(csv.DictReader(stream, delimiter="\t"))
    if len({r["candidate_id"] for r in review_rows}) != len(review_rows):
        raise ValueError("duplicate print review")
    verified_sources, records = {}, []
    for review in sorted(review_rows, key=lambda r: r["candidate_id"]):
        candidate = by_id[review["candidate_id"]]
        if review["status"] not in {"visually_reviewed_publication_identity", "visually_reviewed_print_publication"} or not review["evidence_note"].strip():
            raise ValueError("missing visual print review")
        if digest(candidate["raw_text"].encode("utf-8")) != review["candidate_text_sha256"]:
            raise ValueError("stale print candidate text")
        label = candidate["source_label"]
        source = sources[label]
        if source["sha256"] != candidate["pdf_sha256"]:
            raise ValueError("stale registered print PDF")
        if label not in verified_sources:
            pdf = Path(source["filename"])
            if file_digest(pdf) != candidate["pdf_sha256"]:
                raise ValueError("stale registered print PDF")
            ocr = pdf.with_suffix(".vision.txt")
            verified_sources[label] = (file_digest(ocr), ocr.read_bytes().decode("utf-8", errors="strict"))
        ocr_sha, text = verified_sources[label]
        if not 0 <= candidate["start"] < candidate["end"] <= len(text):
            raise ValueError("invalid print OCR span")
        if ocr_sha != candidate["ocr_sha256"] or text[candidate["start"]:candidate["end"]] != candidate["raw_text"]:
            raise ValueError("stale print OCR span")
        page_headers = [h for h in PAGE.finditer(text) if h.end() <= candidate["start"]]
        if not page_headers or int(page_headers[-1][1]) != candidate["scan_page"]:
            raise ValueError("print span disagrees with scan page")
        if any(candidate["start"] <= h.start() < candidate["end"] for h in PAGE.finditer(text)):
            raise ValueError("cross-page print import requires a multi-span review")
        transcription = review["verified_transcription"]
        if not transcription.strip():
            raise ValueError("missing verified print transcription")
        authority = None
        if review["status"] == "visually_reviewed_print_publication":
            if review["online_occurrence_id"] or review["online_source_sha256"]:
                raise ValueError("print-only publication must not imply an online crosswalk")
            label = review.get("publication_label", "").strip()
            year = review.get("publication_year", "")
            if not label or not re.fullmatch(r"(?:1[5-9]|20)\d{2}[a-z]?", year):
                raise ValueError("print publication requires reviewed label/year")
            # Identity is source-specific, not deduced from author/year spelling.
            authority = {"id": "publication-print-" + digest(candidate["id"].encode())[:32],
                         "kind": "publication", "label": label, "year": year,
                         "scope": "published_print", "status": "reviewed_print_identity"}
            authority_id, online_id = authority["id"], None
        else:
            row = online.get(review["online_occurrence_id"])
            if not row or row["kind"] != "publication" or row["source_sha256"] != review["online_source_sha256"]:
                raise ValueError("stale online publication crosswalk")
            authority_id, online_id = row["id"], row["occurrence_id"]
        records.append({"id": "print-occurrence-" + digest(dumps(review).encode())[:32],
                        "authority_id": authority_id, "online_occurrence_id": online_id,
                        "authority": authority,
                        "candidate": candidate, "verified_transcription": transcription,
                        "review": review, "review_sha256": file_digest(reviews),
                        "status": review["status"], "scope": "published_print",
                        "limitations": "Publication identity only; citation editions remain unverified"})
    return records


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
