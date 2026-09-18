from __future__ import annotations

import csv
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from badw_dual_identity import run  # noqa: E402


FIELDS = ["page", "line", "entry_id", "zone", "headword_tibetan", "headword_latin", "line_text"]


def _tsv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    qa_root = tmp_path / "qa"
    rows = [
        {"page": "240", "line": "1", "entry_id": "1", "zone": "headword_line", "headword_tibetan": "ཀ", "headword_latin": "ka", "line_text": "ཀ ka"},
        {"page": "241", "line": "1", "entry_id": "2", "zone": "headword_line", "headword_tibetan": "ཁ", "headword_latin": "kha", "line_text": "ཁ kha"},
        {"page": "242", "line": "1", "entry_id": "3", "zone": "headword_line", "headword_tibetan": "ག", "headword_latin": "ga", "line_text": "ག ga"},
    ]
    _tsv(qa_root / "wts_1_34/wts_1_34_line_zones.tsv", FIELDS, rows)
    for volume in ("wts_35_51", "wts_8_b", "wts_9_m"):
        _tsv(qa_root / volume / f"{volume}_line_zones.tsv", FIELDS, [])
    sources = [
        {"source_id": "badw:html:db", "delivery_type": "database_article", "lemma": "ka", "homonym": "1", "tibetan": "ཀ", "source_text": "not used", "provenance": {}},
        {"source_id": "badw:pdf:good", "delivery_type": "generated_pdf_span", "lemma": "kha", "homonym": "", "tibetan": "ཁ", "source_text": "not used", "provenance": {}},
        {"source_id": "badw:pdf:duplicate", "delivery_type": "generated_pdf_span", "lemma": "ka", "homonym": "", "tibetan": "ཀ", "source_text": "not used", "provenance": {}},
        {"source_id": "badw:pdf:one", "delivery_type": "generated_pdf_span", "lemma": "ka", "homonym": "", "tibetan": "ང", "source_text": "not used", "provenance": {}},
        {"source_id": "badw:pdf:page", "delivery_type": "generated_pdf_span", "lemma": "za", "homonym": "", "tibetan": "ཞ", "source_text": "not used", "provenance": {}},
        {"source_id": "badw:pdf:none", "delivery_type": "generated_pdf_span", "lemma": "na", "homonym": "", "tibetan": "ན", "source_text": "not used", "provenance": {}},
    ]
    sources.sort(key=lambda row: str(row["source_id"]))
    source_path = tmp_path / "sources.jsonl"
    source_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in sources), encoding="utf-8")
    def candidate(source_id: str, anchor: str, latin: bool, tibetan: bool, page: bool, rank: int = 1) -> dict[str, object]:
        return {"source_id": source_id, "local_anchor_id": anchor, "local_volume": "wts_1_34", "legacy_entry_ids": ["1"], "local_start_page": 1, "local_start_line": 1, "local_pages": [1], "rank": rank, "score": 0.0, "latin_exact": latin, "tibetan_exact": tibetan, "printed_page_exact": page}
    candidates = [
        candidate("badw:html:db", "wts_1_34:240:1", True, True, False),
        candidate("badw:pdf:good", "wts_1_34:241:1", True, True, True),
        candidate("badw:pdf:duplicate", "wts_1_34:240:1", True, True, False),
        candidate("badw:pdf:duplicate", "wts_1_34:242:1", True, True, False, 2),
        candidate("badw:pdf:one", "wts_1_34:240:1", True, False, False),
        candidate("badw:pdf:page", "wts_1_34:242:1", False, False, True),
    ]
    candidate_path = tmp_path / "candidates.jsonl"
    candidate_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in candidates), encoding="utf-8")
    matches = tmp_path / "matches.tsv"
    _tsv(matches, ["source_id"], [{"source_id": row["source_id"]} for row in sources])
    return source_path, candidate_path, matches, qa_root


def test_dual_evidence_requires_pdf_page_and_never_promotes_page_only(tmp_path: Path):
    source, candidates, matches, qa = _fixture(tmp_path)
    summary = run(source, candidates, matches, qa, tmp_path / "result")
    rows = {row["source_id"]: row for row in (
        json.loads(line) for line in (tmp_path / "result/witness_assessments.jsonl").read_text(encoding="utf-8").splitlines()
    )}
    assert rows["badw:pdf:good"]["disposition"] == "confident_dual_evidence"
    assert rows["badw:html:db"]["reason"] == "database_requires_independent_source_discriminator"
    assert rows["badw:pdf:duplicate"]["reason"] == "duplicate_exact_heading"
    assert rows["badw:pdf:one"]["reason"] == "one_field_only"
    assert rows["badw:pdf:page"]["reason"] == "pdf_page_only"
    assert rows["badw:pdf:none"]["disposition"] == "unmatched"
    assert summary["dispositions"] == {"candidate_only": 4, "confident_dual_evidence": 1, "unmatched": 1}


def test_dual_identity_output_is_byte_identical_and_preserves_unicode(tmp_path: Path):
    source, candidates, matches, qa = _fixture(tmp_path)
    source.write_text(source.read_text(encoding="utf-8").replace('"ka"', '"ḱa"', 1), encoding="utf-8")
    one, two = tmp_path / "one", tmp_path / "two"
    run(source, candidates, matches, qa, one)
    run(source, candidates, matches, qa, two)
    for name in ("local_heading_inventory.jsonl", "witness_assessments.jsonl", "candidate_classifications.jsonl", "summary.json"):
        assert (one / name).read_bytes() == (two / name).read_bytes()
    assert "ḱa" in (one / "witness_assessments.jsonl").read_text(encoding="utf-8")
