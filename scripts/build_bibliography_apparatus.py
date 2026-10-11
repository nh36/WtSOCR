#!/usr/bin/env python3
"""Capture the registered corpus and located apparatus without asserting identities.

An OCR page is evidence, not a bibliography occurrence. Zone envelopes may
overlap and include dictionary text on two-up scans. No record splitting,
normalization, reconciliation, or absence inference is performed here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from badw_bibliography import BASE, PAGES, dumps, file_digest, parse_page, write_jsonl
from badw_source_cache import RequestSpec, SourceCache

ROOT = Path(__file__).resolve().parents[1]
PAGE = re.compile(r"^=== page (\d+) ===\r?\n", re.M)
VERSION = "wts-apparatus-census-v1"


def tsv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return [row for row in csv.DictReader(stream, delimiter="\t")
                if any(row.values())]


def page_spans(text: str, count: int) -> list[tuple[int, int, int]]:
    headers = list(PAGE.finditer(text))
    if [int(h[1]) for h in headers] != list(range(1, count + 1)):
        raise ValueError("OCR must contain every registered scan page once, in order")
    # Include page markers. Prepending the separately retained preamble to
    # the concatenated slices reproduces the entire file.
    return [(int(h[1]), h.start(), headers[i + 1].start()
             if i + 1 < len(headers) else len(text))
            for i, h in enumerate(headers)]


def capture_print(registry: Path, inventory: Path, root: Path) -> tuple[list, list, list]:
    sources, zones = tsv(registry), tsv(inventory)
    if len({s["label"] for s in sources}) != len(sources):
        raise ValueError("duplicate registered source")
    if len({z["zone_id"] for z in zones}) != len(zones):
        raise ValueError("duplicate apparatus zone")
    by_label = {s["label"]: s for s in sources}
    for z in zones:
        if z["source_label"] not in by_label:
            raise ValueError("unregistered apparatus source")
        s = by_label[z["source_label"]]
        if z["pdf_sha256"] != s["sha256"]:
            raise ValueError("zone disagrees with registered PDF hash")
        a, b = int(z["start_scan_page"]), int(z["end_scan_page"])
        if not 1 <= a <= b <= int(s["pages"]):
            raise ValueError("zone outside registered scan")
        if z["review_status"] not in {
                "visually_located_records_unreviewed",
                "visually_reviewed_editorial_classification"} or not z["boundary_note"]:
            raise ValueError("zone requires explicit location review and boundary limitations")
    pages, source_records = [], []
    for s in sources:
        pdf = root / s["filename"]
        if file_digest(pdf) != s["sha256"] or pdf.stat().st_size != int(s["size_bytes"]):
            raise ValueError("registered PDF hash/size mismatch")
        ocr = pdf.with_suffix(".vision.txt")
        ocr_sha = file_digest(ocr)
        text = ocr.read_bytes().decode("utf-8", errors="strict")
        own = [z for z in zones if z["source_label"] == s["label"]]
        if any(z["ocr_sha256"] != ocr_sha for z in own):
            raise ValueError("stale apparatus OCR hash")
        spans = page_spans(text, int(s["pages"]))
        source_records.append({**s, "ocr_sha256": ocr_sha,
                               "ocr_filename": str(ocr.relative_to(root)),
                               "ocr_preamble": text[:spans[0][1]],
                               "survey_status": "complete_ocr_census_visual_census_pending"})
        for page, start, end in spans:
            memberships = [z["zone_id"] for z in own
                           if int(z["start_scan_page"]) <= page <= int(z["end_scan_page"])]
            pages.append({"source_label": s["label"], "scan_page": page,
                          "pdf_sha256": s["sha256"], "ocr_sha256": ocr_sha,
                          "start": start, "end": end, "raw_text": text[start:end],
                          "zone_ids": memberships, "reading_status": "unreviewed_ocr",
                          "apparatus_status": "located_zone_page" if memberships
                          else "not_yet_classified_by_visual_census"})
    return source_records, zones, pages


def build(registry: Path, inventory: Path, questions: Path, cache: Path,
          output: Path, root: Path = ROOT, online_inventory: Path | None = None) -> dict:
    if output.exists():
        raise ValueError("snapshots are immutable; use a new output directory")
    if "work" not in output.resolve().parts:
        raise ValueError("raw source material must remain in ignored work storage")
    sources, zones, pages = capture_print(registry, inventory, root)
    obligations = tsv(questions)
    if not obligations or any(q["state"] != "open" for q in obligations):
        raise ValueError("census snapshot requires explicit open completion obligations")
    online_sources, online_rows, responses = [], [], []
    for page, kind in PAGES.items():
        response = SourceCache(cache).fetch(RequestSpec(BASE + page), offline=True)
        metadata = dict(response.metadata)
        rows = parse_page(response.body, metadata, kind)
        if not rows:
            raise ValueError("empty online apparatus page")
        online_sources.append(metadata)
        online_rows.extend(rows)
        responses.append((page, response.body))
    if len({r["occurrence_id"] for r in online_rows}) != len(online_rows):
        raise ValueError("duplicate online occurrence identity")
    if online_inventory is not None:
        registered_online = tsv(online_inventory)
        observed = {m["requested_url"]: m for m in online_sources}
        row_counts = Counter(r["source_url"] for r in online_rows)
        if len(registered_online) != len(observed) or {r["url"] for r in registered_online} != set(observed):
            raise ValueError("online inventory differs from captured page set")
        for r in registered_online:
            m = observed[r["url"]]
            if (r["sha256"] != m["sha256"] or int(r["size_bytes"]) != m["byte_length"]
                    or int(r["http_status"]) != m["http_status"]
                    or int(r["source_row_count"]) != row_counts[r["url"]]):
                raise ValueError("stale online source inventory")
    manifest = {"contract_version": VERSION, "completeness": "incomplete",
                "sources": sources, "online_sources": online_sources,
                "registry_sha256": file_digest(registry),
                "inventory_sha256": file_digest(inventory),
                "questions_sha256": file_digest(questions),
                "counts": {"located_print_zones": len(zones),
                           "online_zones": len(online_sources),
                           "ocr_pages": len(pages),
                           "located_zone_scan_pages": sum(bool(p["zone_ids"]) for p in pages),
                           "online_source_occurrences": len(online_rows),
                           "online_rows_by_kind": dict(Counter(r["kind"] for r in online_rows)),
                           "visually_transcribed_print_records_in_this_snapshot": 0,
                           "canonical_works": None, "canonical_publications": None,
                           "canonical_sigla": None, "exact_record_duplicates": None,
                           "print_online_discrepancies": None,
                           "print_only_records": None, "online_only_records": None},
                "mim_definition_finding": "unresolved_pending_exhaustive_review",
                "limitations": ["Zone headings are locators, not verified transcriptions.",
                                "Zone envelopes include other material and may overlap.",
                                "Unlocated pages have not been proved apparatus-free.",
                                "Online row authority IDs are not reconciled print identities.",
                                "OCR pages are not bibliographic record occurrences."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".apparatus-", dir=output.parent) as temporary:
        target = Path(temporary)
        write_jsonl(target / "print_sources.jsonl", sources)
        write_jsonl(target / "zones.jsonl", zones)
        write_jsonl(target / "ocr_pages.jsonl", pages)
        write_jsonl(target / "online_sources.jsonl", online_sources)
        write_jsonl(target / "online_occurrences.jsonl", online_rows)
        write_jsonl(target / "open_questions.jsonl", obligations)
        for page, body in responses:
            (target / (page + ".html")).write_bytes(body)
        shutil.copyfile(inventory, target / inventory.name)
        shutil.copyfile(questions, target / questions.name)
        if online_inventory is not None:
            shutil.copyfile(online_inventory, target / online_inventory.name)
            manifest["online_inventory_sha256"] = file_digest(online_inventory)
        with sqlite3.connect(target / "apparatus.sqlite") as db:
            db.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE source(label TEXT PRIMARY KEY, pdf_sha256 TEXT NOT NULL,
                                    ocr_sha256 TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE zone(id TEXT PRIMARY KEY, source_label TEXT NOT NULL REFERENCES source(label),
                                  start_page INTEGER NOT NULL, end_page INTEGER NOT NULL, data TEXT NOT NULL);
                CREATE TABLE ocr_page(source_label TEXT NOT NULL REFERENCES source(label),
                                      scan_page INTEGER NOT NULL, start INTEGER NOT NULL,
                                      end INTEGER NOT NULL, raw_text TEXT NOT NULL,
                                      apparatus_status TEXT NOT NULL, PRIMARY KEY(source_label, scan_page));
                CREATE TABLE zone_page(zone_id TEXT NOT NULL REFERENCES zone(id),
                                       source_label TEXT NOT NULL, scan_page INTEGER NOT NULL,
                                       PRIMARY KEY(zone_id, source_label, scan_page),
                                       FOREIGN KEY(source_label, scan_page) REFERENCES ocr_page(source_label, scan_page));
                CREATE TABLE online_occurrence(id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                                               source_authority_id TEXT NOT NULL,
                                               label_text TEXT NOT NULL, raw_text TEXT NOT NULL,
                                               source_sha256 TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE open_question(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            """)
            db.executemany("INSERT INTO source VALUES(?,?,?,?)", [(s["label"], s["sha256"], s["ocr_sha256"], dumps(s)) for s in sources])
            db.executemany("INSERT INTO zone VALUES(?,?,?,?,?)", [(z["zone_id"], z["source_label"], int(z["start_scan_page"]), int(z["end_scan_page"]), dumps(z)) for z in zones])
            db.executemany("INSERT INTO ocr_page VALUES(?,?,?,?,?,?)", [(p["source_label"], p["scan_page"], p["start"], p["end"], p["raw_text"], p["apparatus_status"]) for p in pages])
            db.executemany("INSERT INTO zone_page VALUES(?,?,?)", [(z, p["source_label"], p["scan_page"]) for p in pages for z in p["zone_ids"]])
            db.executemany("INSERT INTO online_occurrence VALUES(?,?,?,?,?,?,?)", [(r["occurrence_id"], r["kind"], r["id"], r["label_text"], r["text"], r["source_sha256"], dumps(r)) for r in online_rows])
            db.executemany("INSERT INTO open_question VALUES(?,?)", [(q["question_id"], dumps(q)) for q in obligations])
        manifest["artifacts"] = {p.name: file_digest(p) for p in sorted(target.iterdir())}
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        # Publish only after complete validation; a failed capture leaves no snapshot.
        target.rename(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "data/source_pdfs.tsv")
    parser.add_argument("--inventory", type=Path, default=ROOT / "data/bibliography_apparatus_zones.tsv")
    parser.add_argument("--questions", type=Path, default=ROOT / "data/bibliography_apparatus_questions.tsv")
    parser.add_argument("--online-inventory", type=Path, default=ROOT / "data/bibliography_apparatus_online_sources.tsv")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build(args.registry, args.inventory, args.questions, args.cache, args.output,
                     online_inventory=args.online_inventory)
    print(json.dumps({"completeness": manifest["completeness"], **manifest["counts"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
