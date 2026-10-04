"""Lossless print candidates, using synthetic OCR only."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import badw_print_bibliography as printbib


def inputs(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"synthetic scan")
    ocr = pdf.with_suffix(".vision.txt")
    ocr.write_text("=== page 001 ===\nExcluded work\n2. Literature\nPreamble ṅ\nAUTHOR 2001: Title\n"
                   "2002: Other\n=== page 002 ===\nContinuation\nOTHER 2003: Book\n3. Abbreviations\nExcluded\n", encoding="utf-8")
    review = dict(range_id="r", source_label="scan", pdf_sha256=printbib.file_digest(pdf),
                  ocr_sha256=printbib.file_digest(ocr), start_page="1", end_page="2",
                  start_heading="2. Literature", end_heading="3. Abbreviations", evidence_note="reviewed boundaries")
    return pdf, ocr, review


def test_lossless_partition_offsets_and_inherited_authors(tmp_path):
    pdf, ocr, review = inputs(tmp_path)
    pages, candidates = printbib.extract(pdf, ocr, review)
    text = ocr.read_text()
    assert len(pages) == 2
    assert {c["candidate_type"] for c in candidates} == {"unclassified_span", "author_year_candidate", "inherited_year_candidate"}
    for page in pages:
        chunks = [c for c in candidates if c["page_id"] == page["id"]]
        assert "".join(c["raw_text"] for c in chunks) == text[page["selected_start"]:page["selected_end"]]
    for c in candidates:
        assert c["raw_text"] == text[c["start"]:c["end"]]
        assert c["authority_id"] is None and c["preceding_author"] is None
        assert "Excluded" not in c["raw_text"]
    assert (pages, candidates) == printbib.extract(pdf, ocr, review)


def test_stale_missing_ambiguous_and_reversed_ranges(tmp_path):
    pdf, ocr, review = inputs(tmp_path)
    for update, reason in (({"ocr_sha256": "wrong"}, "hash"), ({"end_page": "3"}, "missing OCR"),
                           ({"start_heading": "Missing"}, "heading"), ({"start_page": "2", "end_page": "1"}, "range")):
        with pytest.raises(ValueError, match=reason):
            printbib.extract(pdf, ocr, {**review, **update})


def test_build_reproducible_and_immutable(tmp_path):
    import csv
    pdf, ocr, review = inputs(tmp_path)
    registry = tmp_path / "sources.tsv"
    registry.write_text(f"label\tfilename\tsha256\nscan\t{pdf}\t{review['pdf_sha256']}\n")
    ranges = tmp_path / "ranges.tsv"
    with ranges.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=review, delimiter="\t")
        writer.writeheader()
        writer.writerow(review)
    a, b = tmp_path / "work/a", tmp_path / "work/b"
    assert printbib.build(registry, ranges, a) == printbib.build(registry, ranges, b)
    for file in a.iterdir():
        assert file.read_bytes() == (b / file.name).read_bytes()
    with pytest.raises(ValueError, match="immutable"):
        printbib.build(registry, ranges, a)


def test_reviewed_print_import_is_hash_pinned_and_preserves_variants(tmp_path):
    import csv
    pdf, ocr, review = inputs(tmp_path)
    _, candidates = printbib.extract(pdf, ocr, review)
    c = next(c for c in candidates if c["raw_text"].startswith("AUTHOR 2001"))
    candidate_path = tmp_path / "candidates.jsonl"
    printbib.write_jsonl(candidate_path, candidates)
    registry = tmp_path / "sources.tsv"
    registry.write_text(f"label\tfilename\tsha256\nscan\t{pdf}\t{review['pdf_sha256']}\n")
    online = [{"occurrence_id": "o", "id": "p", "kind": "publication",
               "source_sha256": "onlinehash", "text": "Different online description"}]
    record = dict(candidate_id=c["id"], candidate_text_sha256=printbib.digest(c["raw_text"].encode()),
                  online_occurrence_id="o", online_source_sha256="onlinehash",
                  status="visually_reviewed_publication_identity", verified_transcription="AUTHOR 2001: Title",
                  evidence_note="Synthetic visual review, publication identity only")
    reviews = tmp_path / "reviews.tsv"
    def write(rows):
        with reviews.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=record, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
    write([record])
    result = printbib.reviewed_occurrences(candidate_path, reviews, registry, online)
    assert len(result) == 1  # Other candidates never become authorities.
    assert result[0]["candidate"]["raw_text"] == c["raw_text"]
    assert result[0]["verified_transcription"] != online[0]["text"]
    assert result == printbib.reviewed_occurrences(candidate_path, reviews, registry, online)
    assert online[0]["text"] == "Different online description"
    for update, reason in (({"candidate_text_sha256": "stale"}, "candidate"),
                           ({"online_source_sha256": "stale"}, "crosswalk"),
                           ({"evidence_note": ""}, "visual"),
                           ({"verified_transcription": ""}, "transcription")):
        write([{**record, **update}])
        with pytest.raises(ValueError, match=reason):
            printbib.reviewed_occurrences(candidate_path, reviews, registry, online)
    write([record, record])
    with pytest.raises(ValueError, match="duplicate print review"):
        printbib.reviewed_occurrences(candidate_path, reviews, registry, online)
    write([record])
    changed = [{**candidate, "scan_page": 2} if candidate["id"] == c["id"] else candidate for candidate in candidates]
    printbib.write_jsonl(candidate_path, changed)
    with pytest.raises(ValueError, match="scan page"):
        printbib.reviewed_occurrences(candidate_path, reviews, registry, online)
    printbib.write_jsonl(candidate_path, candidates)
    changed = [{**candidate, "pdf_sha256": "stale"} if candidate["id"] == c["id"] else candidate for candidate in candidates]
    printbib.write_jsonl(candidate_path, changed)
    with pytest.raises(ValueError, match="print PDF"):
        printbib.reviewed_occurrences(candidate_path, reviews, registry, online)
    text = ocr.read_text()
    extended = {**c, "end": text.index("OTHER 2003")}
    extended["raw_text"] = text[extended["start"]:extended["end"]]
    printbib.write_jsonl(candidate_path, [extended])
    write([{**record, "candidate_text_sha256": printbib.digest(extended["raw_text"].encode())}])
    with pytest.raises(ValueError, match="cross-page"):
        printbib.reviewed_occurrences(candidate_path, reviews, registry, online)
    write([record])
    printbib.write_jsonl(candidate_path, candidates)
    ocr.write_text(ocr.read_text() + "changed")
    with pytest.raises(ValueError, match="OCR span"):
        printbib.reviewed_occurrences(candidate_path, reviews, registry, online)
