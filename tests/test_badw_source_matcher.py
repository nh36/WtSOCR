from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from badw_source_matcher import (  # noqa: E402
    LocalEntry,
    SourceArticle,
    build_indexes,
    candidate_record,
    load_pdf_articles,
    materialize_source_snapshot,
    score_article,
    score_candidates,
    tibetan_key,
)


def _run(index: int, text: str, font_id: str) -> dict[str, object]:
    return {
        "run_index": index,
        "decoded_unicode": text,
        "x": 10.0,
        "y": 100.0,
        "font_id": font_id,
        "glyphs": [],
    }


def _write_canonical_page(root: Path) -> None:
    volume = root / "volume_2"
    (volume / "pages").mkdir(parents=True)
    with (volume / "page_occurrences.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["page_id", "canonical_url"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow({"page_id": "v2-p001", "canonical_url": "https://example.test/pdf/ka"})
    page = {
        "page_id": "v2-p001",
        "printed_page": 1,
        "representative_source": {"source_sha256": "a" * 64},
        "representative_fonts": [
            {"font_id": "rabten", "family": "RabtenTibetan", "style": "regular"},
            {"font_id": "regular", "family": "TGaramond", "style": "regular"},
            {"font_id": "italic", "family": "TGaramond", "style": "italic"},
        ],
        "positioned_page": {
            "positioned_text_runs": [
                _run(0, "ཀ", "rabten"), _run(1, "2", "regular"), _run(2, "ka", "italic"),
                _run(3, " first article", "regular"), _run(4, "ཁ", "rabten"),
                _run(5, "kha", "italic"), _run(6, " second article", "regular"),
            ],
            "tibetan_text_candidates": [
                {"candidate_index": 0, "kind": "body_tibetan_text", "decoded_unicode": "ཀ",
                 "run_indices": [0], "unknown_glyphs": 0, "x": 10.0, "y": 100.0},
                {"candidate_index": 1, "kind": "body_tibetan_text", "decoded_unicode": "ཁ",
                 "run_indices": [4], "unknown_glyphs": 0, "x": 10.0, "y": 100.0},
            ],
        },
    }
    with gzip.open(volume / "pages/v2-p001.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(page, handle, ensure_ascii=False, sort_keys=True)
    for number in (3, 4):
        directory = root / f"volume_{number}"
        directory.mkdir()
        (directory / "page_occurrences.tsv").write_text("page_id\tcanonical_url\n", encoding="utf-8")
        (directory / "pages").mkdir()


def test_pdf_source_spans_preserve_loc_heading_and_exact_provenance(tmp_path: Path):
    _write_canonical_page(tmp_path)
    sources = load_pdf_articles(tmp_path)
    assert [(source.lemma, source.homonym, source.tibetan) for source in sources] == [
        ("ka", "2", "ཀ"), ("kha", "", "ཁ")
    ]
    assert sources[0].provenance["run_start"] == 0
    assert sources[0].provenance["run_end_exclusive"] == 4
    assert sources[0].provenance["loc_run_indices"] == "2"
    assert sources[1].text.endswith(" second article")


def test_matcher_requires_unambiguous_article_identity():
    matching = LocalEntry("wts_1_34", "1", "ka", "ཀ", (240,), "ཀ ka exact first article")
    competing = LocalEntry("wts_1_34", "2", "ka", "ཁ", (241,), "ཁ ka unrelated")
    entries, latin, tibetan, page = build_indexes([matching, competing])
    source = SourceArticle(
        "badw:pdf:v2-p001:0", "generated_pdf_span", "ka", "2", "ཀ",
        "ཀ ka exact first article", {"volume": 2, "printed_page": 1},
    )
    result = score_article(source, entries, latin, tibetan, page)
    assert result["confidence"] == "high"
    assert result["entry"] == matching
    assert result["latin_exact"] and result["tibetan_exact"]


def test_tibetan_key_preserves_only_comparison_relevant_tibetan():
    assert tibetan_key(" ཀ༌་ 2 ") == "ཀ"


def test_candidate_evidence_retains_ambiguous_identity_in_deterministic_order():
    first = LocalEntry("wts_1_34", "1", "ka", "ཀ", (240,), "first")
    second = LocalEntry("wts_1_34", "2", "ka", "ཀ", (241,), "second")
    entries, latin, tibetan, page = build_indexes([second, first])
    source = SourceArticle(
        "badw:html:ka/1", "database_article", "ka", "1", "ཀ", "source", {}
    )
    candidates = score_candidates(source, entries, latin, tibetan, page)
    assert [candidate["entry"].entry_id for candidate in candidates] == ["1", "2"]
    assert [candidate["rank"] for candidate in candidates] == [1, 2]
    assert score_article(source, entries, latin, tibetan, page)["confidence"] == "low"
    record = candidate_record(source, candidates[0])
    assert record == {
        "contract_version": "badw-source-match-candidate-v1",
        "source_id": "badw:html:ka/1",
        "delivery_type": "database_article",
        "local_volume": "wts_1_34",
        "local_entry_id": "1",
        "rank": 1,
        "score": 0.82,
        "latin_exact": True,
        "tibetan_exact": True,
        "printed_page_exact": False,
        "local_pages": [240],
    }


def test_existing_source_snapshot_is_copied_without_reparsing_or_reordering(tmp_path: Path):
    source = tmp_path / "source.jsonl"
    source.write_text(
        json.dumps({
            "source_id": "badw:one", "delivery_type": "database_article",
            "lemma": "ka", "homonym": "1", "tibetan": "ཀ", "source_text": "source",
            "provenance": {},
        }, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    destination = tmp_path / "copied.jsonl"
    assert materialize_source_snapshot(source, None, None, destination) == 1
    assert destination.read_bytes() == source.read_bytes()
