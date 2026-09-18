from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from wtsocr_entry_segmentation import anchor_records, inventory, read_rows  # noqa: E402


def _row(page: int, line: int, entry_id: int, zone: str, tibetan: str = "", latin: str = "", text: str = "") -> dict[str, str]:
    return {
        "page": str(page), "line": str(line), "entry_id": str(entry_id), "zone": zone,
        "headword_tibetan": tibetan, "headword_latin": latin, "line_text": text,
    }


def test_headword_anchors_split_a_legacy_entry_without_changing_unicode():
    rows = [
        _row(1, 1, 1, "headword_line", "དཀར་ཅི་", "ci", "དཀར་ཅི་ dkar ci first"),
        _row(1, 2, 1, "german_prose", text="first definition"),
        _row(1, 3, 1, "headword_line", "དཀར་ཆུང་", "chuṅ", "དཀར་ཆུང་ dkar chuṅ second"),
    ]
    anchors = anchor_records("wts_1_34", rows)
    assert [anchor["anchor_id"] for anchor in anchors] == ["wts_1_34:1:1", "wts_1_34:1:3"]
    assert anchors[0]["end_line"] == 2
    assert anchors[0]["headword_tibetan"] == "དཀར་ཅི་"
    assert anchors[0]["headword_loc_display"] == "dkar ci"
    assert anchors[1]["legacy_entry_ids"] == ["1"]


def test_inventory_is_deterministic_and_records_missing_and_multiple_legacy_ids(tmp_path: Path):
    qa = tmp_path / "qa"
    fields = ["page", "line", "entry_id", "zone", "headword_tibetan", "headword_latin", "line_text"]
    for volume in ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"):
        directory = qa / volume
        directory.mkdir(parents=True)
        rows = [] if volume != "wts_1_34" else [
            _row(1, 1, 1, "headword_line", "ཀ", "ka", "ཀ ka"),
            _row(1, 2, 1, "headword_line", "ཁ", "kha", "ཁ kha"),
            _row(1, 3, 2, "german_prose", text="unheaded"),
        ]
        with (directory / f"{volume}_line_zones.tsv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert inventory(qa, first)["headword_anchors"] == 2
    inventory(qa, second)
    assert (first / "anchors.jsonl").read_bytes() == (second / "anchors.jsonl").read_bytes()
    issues = list(csv.DictReader((first / "legacy_entry_issues.tsv").open(encoding="utf-8"), delimiter="\t"))
    assert issues == [
        {"volume": "wts_1_34", "legacy_entry_id": "1", "headword_anchor_count": "2", "issue": "multiple_headword_anchors"},
        {"volume": "wts_1_34", "legacy_entry_id": "2", "headword_anchor_count": "0", "issue": "missing_headword_anchor"},
    ]
    first_record = json.loads((first / "anchors.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first_record["headword_tibetan"] == "ཀ"


def test_non_increasing_qa_coordinates_are_rejected(tmp_path: Path):
    path = tmp_path / "zones.tsv"
    path.write_text(
        "page\tline\tentry_id\tzone\theadword_tibetan\theadword_latin\tline_text\n"
        "1\t2\t1\theadword_line\tཀ\tka\tཀ ka\n"
        "1\t1\t1\tgerman_prose\t\t\ttext\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-increasing"):
        read_rows(path)
