"""Synthetic, offline tests for the PDF-structure gold-set harness."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from benchmark_badw_pdf_structure import materialize_gold, predictions, score, select


def _article(volume: int, suffix: int) -> dict:
    text = "1. Wort „meaning“ (Siddh 11.2) ↑other"
    return {"article_id": f"article:{volume}:{suffix}", "volume": volume,
        "loc_headword": f"head{suffix}", "tibetan_headword": "ཁ་",
        "source_faithful_sha256": sha256(text.encode()).hexdigest(),
        "visual_lines": [{"text": text}],
        "divisions": [{"kind": "numbered_sense", "label": "1", "start_line_index": 0}],
        "diagnostics": {"numbered_senses": 1, "unknown_glyphs": 0},
        "candidates": {"german_quotes": [{"visual_start": 8, "visual_end": 17}],
                       "parenthetical_citations": [{"visual_start": 18, "visual_end": 31}],
                       "cross_references": [{"visual_start": 32, "visual_end": 38}],
                       "adjacent_quote_citation_pairs": [{"quote_index": 0, "citation_index": 0}]}}


def test_selection_is_stratified_and_input_order_independent() -> None:
    articles = [_article(volume, suffix) for volume in (2, 3, 4) for suffix in range(5)]
    first = select(articles, per_volume=3)
    second = select(reversed(articles), per_volume=3)
    assert first == second
    assert [row["volume"] for row in first] == [2] * 3 + [3] * 3 + [4] * 3
    assert len({row["article_id"] for row in first}) == 9


def test_independent_selection_excludes_prior_sample() -> None:
    articles = [_article(volume, suffix) for volume in (2, 3, 4) for suffix in range(6)]
    prior = select(articles, per_volume=2)
    excluded = {row["article_id"] for row in prior}
    holdout = select(articles, per_volume=2, exclude_ids=excluded)
    assert len(holdout) == 6
    assert excluded.isdisjoint(row["article_id"] for row in holdout)
    assert holdout == select(reversed(articles), per_volume=2, exclude_ids=excluded)


def test_predictions_and_gold_are_exact_spans() -> None:
    row = select([_article(volume, 0) for volume in (2, 3, 4)], per_volume=1)[0]
    assert row["predictions"]["numbered_sense"] == [(0, 2)]
    assert row["predictions"]["definition"] == []
    gold = {"article_id": row["article_id"],
        "source_faithful_sha256": row["source_faithful_sha256"],
        "visual_sha256": row["visual_sha256"], "reviewed_end": row["reviewed_end"],
        "reviewed_kinds": ["numbered_sense", "german_quote", "definition", "parenthetical_citation"],
        "spans": [{"kind": "numbered_sense", "start": 0, "end": 2, "text": "1."},
                  {"kind": "german_quote", "start": 8, "end": 17, "text": "„meaning“"},
                  {"kind": "definition", "start": 3, "end": 7, "text": "Wort"}]}
    metrics = score([row], [gold])["metrics"]
    assert metrics["german_quote"]["true_positive"] == 1
    assert metrics["definition"]["false_negative"] == 1
    assert metrics["parenthetical_citation"]["false_positive"] == 1
    assert metrics["belegstelle"]["gold"] == 0


def test_gold_must_match_source_and_text() -> None:
    row = select([_article(volume, 0) for volume in (2, 3, 4)], per_volume=1)[0]
    gold = {"article_id": row["article_id"],
        "source_faithful_sha256": "0" * 64, "visual_sha256": row["visual_sha256"],
        "reviewed_end": row["reviewed_end"], "reviewed_kinds": ["german_quote"], "spans": []}
    with pytest.raises(ValueError, match="source/review boundary"):
        score([row], [gold])
    gold["source_faithful_sha256"] = row["source_faithful_sha256"]
    gold["spans"] = [{"kind": "german_quote", "start": 8, "end": 17, "text": "wrong"}]
    with pytest.raises(ValueError, match="gold text mismatch"):
        score([row], [gold])


def test_duplicate_article_fails_closed() -> None:
    articles = [_article(volume, 0) for volume in (2, 3, 4)]
    with pytest.raises(ValueError, match="duplicate article_id"):
        select(articles + [articles[0]], per_volume=1)


def test_review_boundary_excludes_truncated_prediction() -> None:
    result = predictions(_article(2, 0), review_end=12)
    assert result["numbered_sense"] == [(0, 2)]
    assert result["german_quote"] == []


def test_manual_literal_annotations_resolve_and_require_review_marker() -> None:
    row = select([_article(volume, 0) for volume in (2, 3, 4)], per_volume=1)[0]
    marker = {"sample_index": "0", "article_id": row["article_id"],
              "kind": "reviewed", "text": "definition", "occurrence": ""}
    span = dict(marker, kind="definition", text="Wort")
    gold = materialize_gold([row], [marker, span])
    assert gold[0]["spans"] == [{"kind": "definition", "start": 3, "end": 7, "text": "Wort"}]
    assert gold[0]["reviewed_kinds"] == ["definition"]
    with pytest.raises(ValueError, match="without reviewed"):
        materialize_gold([row], [span])
    with pytest.raises(ValueError, match="article identity mismatch"):
        materialize_gold([row], [dict(marker, article_id="wrong")])
