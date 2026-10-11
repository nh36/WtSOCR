"""Census coverage is separate from reviewed bibliographic identity."""
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_bibliography_apparatus as apparatus
from badw_source_cache import CacheMissError


def write_tsv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def inputs(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"synthetic registered PDF")
    ocr = pdf.with_suffix(".vision.txt")
    text = "preamble\r\n=== page 001 ===\r\nTitle ṅ\r\n=== page 002 ===\nContinuation\n"
    ocr.write_bytes(text.encode())
    registry, inventory = tmp_path / "registry.tsv", tmp_path / "inventory.tsv"
    source = dict(label="scan", filename="scan.pdf", pages="2", size_bytes=str(pdf.stat().st_size), sha256=apparatus.file_digest(pdf))
    zone = dict(zone_id="z", source_label="scan", pdf_sha256=source["sha256"],
                ocr_sha256=apparatus.file_digest(ocr), start_scan_page="1", end_scan_page="2",
                review_status="visually_located_records_unreviewed", boundary_note="Mixed scan; all records unreviewed.")
    write_tsv(registry, [source])
    write_tsv(inventory, [zone])
    return registry, inventory, pdf, ocr, zone, text


def test_census_replays_all_bytes_and_keeps_overlapping_zones(tmp_path):
    registry, inventory, _, _, zone, text = inputs(tmp_path)
    second = {**zone, "zone_id": "second", "start_scan_page": "2"}
    write_tsv(inventory, [zone, second])
    sources, zones, pages = apparatus.capture_print(registry, inventory, tmp_path)
    assert sources[0]["ocr_preamble"] + "".join(p["raw_text"] for p in pages) == text
    assert len(zones) == 2 and pages[1]["zone_ids"] == ["z", "second"]
    assert all(p["reading_status"] == "unreviewed_ocr" for p in pages)
    assert all("authority_id" not in p for p in pages)
    for p in pages:
        assert text[p["start"]:p["end"]] == p["raw_text"]


@pytest.mark.parametrize("markers", ["=== page 002 ===\n", "=== page 001 ===\n=== page 001 ===\n", "=== page 002 ===\n=== page 001 ===\n"])
def test_missing_duplicate_or_reordered_pages_fail_closed(markers):
    with pytest.raises(ValueError, match="every registered scan page"):
        apparatus.page_spans(markers, 2)


@pytest.mark.parametrize("changed", ["pdf", "ocr", "zone", "range"])
def test_stale_or_invalid_provenance_rejected(tmp_path, changed):
    registry, inventory, pdf, ocr, zone, _ = inputs(tmp_path)
    if changed == "pdf":
        pdf.write_bytes(b"replacement scan")
    elif changed == "ocr":
        ocr.write_bytes(ocr.read_bytes() + b"new text")
    elif changed == "zone":
        write_tsv(inventory, [{**zone, "pdf_sha256": "0" * 64}])
    else:
        write_tsv(inventory, [{**zone, "end_scan_page": "3"}])
    with pytest.raises(ValueError):
        apparatus.capture_print(registry, inventory, tmp_path)


def test_unlocated_page_is_not_evidence_of_absence(tmp_path):
    registry, inventory, _, _, zone, _ = inputs(tmp_path)
    write_tsv(inventory, [{**zone, "end_scan_page": "1"}])
    _, _, pages = apparatus.capture_print(registry, inventory, tmp_path)
    assert pages[1]["zone_ids"] == []
    assert pages[1]["apparatus_status"] == "not_yet_classified_by_visual_census"


def test_editorial_classification_does_not_promote_ocr_to_reviewed_reading(tmp_path):
    registry, inventory, _, _, zone, _ = inputs(tmp_path)
    write_tsv(inventory, [{**zone, "review_status": "visually_reviewed_editorial_classification"}])
    _, zones, pages = apparatus.capture_print(registry, inventory, tmp_path)
    assert zones[0]["review_status"] == "visually_reviewed_editorial_classification"
    assert all(p["reading_status"] == "unreviewed_ocr" for p in pages)


def test_checked_in_editorial_page_provenance():
    root = Path(__file__).resolve().parents[1]
    zones = {r["zone_id"]: r for r in apparatus.tsv(root / "data/bibliography_apparatus_zones.tsv")}
    sources = {r["label"]: r for r in apparatus.tsv(root / "data/source_pdfs.tsv")}
    readings = [json.loads(line) for line in
                (root / "data/bibliography_apparatus_editorial_pages.jsonl").read_text().splitlines()]
    assert len({(r["zone_id"], r["scan_page"]) for r in readings}) == len(readings)
    for reading in readings:
        zone = zones[reading["zone_id"]]
        label = reading["source_label"]
        span = reading["source_span"]
        assert span["end"] - span["start"] == len(span["raw_text"])
        assert int(apparatus.PAGE.match(span["raw_text"])[1]) == reading["scan_page"]
        assert reading["ocr_sha256"] == zone["ocr_sha256"]
        assert reading["pdf_sha256"] == zone["pdf_sha256"] == sources[label]["sha256"]
        assert int(zone["start_scan_page"]) <= reading["scan_page"] <= int(zone["end_scan_page"])
        assert reading["reading_status"] == "unreviewed_ocr_preserved"
        if reading["record_overlap_zone"]:
            overlap = zones[reading["record_overlap_zone"]]
            assert overlap["source_label"] == label
            assert int(overlap["start_scan_page"]) <= reading["scan_page"] <= int(overlap["end_scan_page"])
    for identity in {r["zone_id"] for r in readings}:
        zone = zones[identity]
        assert {r["scan_page"] for r in readings if r["zone_id"] == identity} == set(
            range(int(zone["start_scan_page"]), int(zone["end_scan_page"]) + 1))


def test_failed_offline_capture_does_not_publish_snapshot(tmp_path):
    registry, inventory, _, _, _, _ = inputs(tmp_path)
    questions = tmp_path / "questions.tsv"
    write_tsv(questions, [dict(question_id="q", state="open")])
    output = tmp_path / "work" / "snapshot"
    with pytest.raises(CacheMissError):
        apparatus.build(registry, inventory, questions, tmp_path / "cache", output, tmp_path)
    assert not output.exists()


def test_existing_snapshot_cannot_be_overwritten(tmp_path):
    output = tmp_path / "work" / "snapshot"
    output.mkdir(parents=True)
    with pytest.raises(ValueError, match="immutable"):
        apparatus.build(tmp_path, tmp_path, tmp_path, tmp_path, output)


def test_snapshot_retains_competing_online_occurrences_without_merging(tmp_path, monkeypatch):
    registry, inventory, _, _, _, _ = inputs(tmp_path)
    questions = tmp_path / "questions.tsv"
    write_tsv(questions, [dict(question_id="q", state="open")])

    class OfflineCache:
        def __init__(self, _):
            pass

        def fetch(self, request, offline=False):
            assert offline
            kind = apparatus.PAGES[request.url.rsplit("/", 1)[-1]]
            left, right = {"work": ("textsiglum", "textallg"),
                           "publication": ("autor_jahr", "titel_etc"),
                           "abbreviation": ("", "")}[kind]
            # Same literal label, conflicting descriptions: two occurrences.
            body = ('<div class="content"><table>' + ''.join(
                f'<tr><td class="{left}">Same 2001</td><td class="{right}">{text}</td></tr>'
                for text in ['First ṅ', 'Other edition']) + '</table></div>').encode()
            return SimpleNamespace(body=body, metadata=dict(
                sha256=hashlib.sha256(body).hexdigest(), http_status=200,
                requested_url=request.url, final_url=request.url,
                fetched_at_utc="2026-10-10T00:00:00+00:00",
                response_headers={"content-type": "text/html; charset=utf-8"}))

    monkeypatch.setattr(apparatus, "SourceCache", OfflineCache)
    output = tmp_path / "work" / "snapshot"
    manifest = apparatus.build(registry, inventory, questions, tmp_path, output, tmp_path)
    assert manifest["completeness"] == "incomplete"
    assert manifest["counts"]["canonical_publications"] is None
    assert manifest["counts"]["exact_record_duplicates"] is None
    assert manifest["counts"]["online_source_occurrences"] == 6
    rows = [json.loads(line) for line in (output / "online_occurrences.jsonl").read_text().splitlines()]
    assert len({r["occurrence_id"] for r in rows}) == 6
    with sqlite3.connect(output / "apparatus.sqlite") as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT COUNT(*) FROM online_occurrence").fetchone()[0] == 6
    assert (output / "bibliographie.html").read_bytes().find('First ṅ'.encode()) >= 0
