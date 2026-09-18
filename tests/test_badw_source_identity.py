from __future__ import annotations

import csv
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from badw_source_identity import build_identity_graph, run  # noqa: E402


def _write_tsv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "source.jsonl"
    source.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in [
        {"source_id": "badw:html:ka", "delivery_type": "database_article", "lemma": "ka",
         "homonym": "", "tibetan": "ཀ", "source_text": "original Unicode ś", "provenance": {"sha256": "a"}},
        {"source_id": "badw:pdf:v2-p1:0", "delivery_type": "generated_pdf_span", "lemma": "kha",
         "homonym": "2", "tibetan": "ཁ", "source_text": "source body", "provenance": {"sha256": "b"}},
        {"source_id": "badw:html:ga", "delivery_type": "database_article", "lemma": "ga",
         "homonym": "", "tibetan": "ག", "source_text": "unmatched", "provenance": {"sha256": "c"}},
    ]) + "\n", encoding="utf-8")
    fields = ["source_id", "matched", "confidence", "candidate_count", "score", "margin", "latin_exact",
              "tibetan_exact", "local_volume", "local_entry_id"]
    matches = tmp_path / "matches.tsv"
    _write_tsv(matches, fields, [
        {"source_id": "badw:html:ka", "matched": "True", "confidence": "high", "candidate_count": "1",
         "score": "0.82", "margin": "0.82", "latin_exact": "True", "tibetan_exact": "True",
         "local_volume": "wts_1_34", "local_entry_id": "10"},
        {"source_id": "badw:pdf:v2-p1:0", "matched": "True", "confidence": "medium", "candidate_count": "2",
         "score": "0.41", "margin": "0.06", "latin_exact": "True", "tibetan_exact": "False",
         "local_volume": "wts_1_34", "local_entry_id": "11"},
        {"source_id": "badw:html:ga", "matched": "False", "confidence": "none", "candidate_count": "0",
         "score": "", "margin": "", "latin_exact": "", "tibetan_exact": "", "local_volume": "", "local_entry_id": ""},
    ])
    qa = tmp_path / "qa/wts_1_34"
    _write_tsv(qa / "wts_1_34_line_zones.tsv", ["page", "entry_id", "zone", "headword_tibetan", "headword_latin", "line_text"], [
        {"page": "1", "entry_id": "10", "zone": "headword_line", "headword_latin": "ka", "headword_tibetan": "ཀ", "line_text": "ka"},
        {"page": "2", "entry_id": "11", "zone": "headword_line", "headword_latin": "kha", "headword_tibetan": "ཁ", "line_text": "kha"},
        {"page": "3", "entry_id": "12", "zone": "headword_line", "headword_latin": "nga", "headword_tibetan": "ང", "line_text": "nga"},
    ])
    for volume in ("wts_35_51", "wts_8_b", "wts_9_m"):
        _write_tsv(qa.parent / volume / f"{volume}_line_zones.tsv",
                   ["page", "entry_id", "zone", "headword_tibetan", "headword_latin", "line_text"], [])
    inventory = tmp_path / "scan_only.tsv"
    _write_tsv(inventory, ["volume", "scan_page", "classification", "evidence"], [
        {"volume": "2", "scan_page": "273", "classification": "fascicle_copyright_acknowledgements", "evidence": "x"},
    ])
    return source, matches, qa.parent, inventory


def test_identity_graph_keeps_witnesses_and_candidates_separate(tmp_path: Path):
    source, matches, qa, inventory = _fixture(tmp_path)
    witnesses, clusters, summary = build_identity_graph(source, matches, qa, inventory)
    by_source = {record["source_id"]: record for record in witnesses}
    assert by_source["badw:html:ka"]["linked_cluster_id"] == "wtsocr-local:wts_1_34:10"
    assert by_source["badw:pdf:v2-p1:0"]["local_identity_disposition"] == "candidate_only"
    assert by_source["badw:pdf:v2-p1:0"]["linked_cluster_id"] is None
    assert by_source["badw:html:ga"]["local_identity_disposition"] == "unmatched"
    assert summary["dispositions"] == {"candidate_only": 1, "confident_link": 1, "unmatched": 1}
    assert summary["scan_only_registered_pages"] == 1
    assert len(clusters) == 3


def test_snapshot_and_graph_are_reproducible(tmp_path: Path):
    source, matches, qa, inventory = _fixture(tmp_path)
    one, two = tmp_path / "one", tmp_path / "two"
    run(source, matches, qa, one, inventory)
    run(source, matches, qa, two, inventory)
    for name in ("source_snapshot.json", "witnesses.jsonl", "provisional_local_clusters.jsonl", "summary.json"):
        assert (one / name).read_bytes() == (two / name).read_bytes()
