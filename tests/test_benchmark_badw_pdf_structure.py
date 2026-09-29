"""Synthetic, offline tests for the PDF-structure gold-set harness."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from benchmark_badw_pdf_structure import (
    materialize_gold, predictions, refresh_predictions, score, select,
    with_lexical_predictions,
)


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


def test_selection_can_exceed_eight_per_volume() -> None:
    articles = [_article(volume, suffix) for volume in (2, 3, 4) for suffix in range(30)]
    chosen = select(articles, per_volume=24)
    assert len(chosen) == 72
    assert chosen == select(reversed(articles), per_volume=24)


def test_numbered_sense_span_excludes_visual_indent() -> None:
    article = _article(2, 0)
    article["visual_lines"][0]["text"] = " 2. Wort"
    article["divisions"][0]["label"] = "2"
    assert predictions(article, 8)["numbered_sense"] == [(1, 3)]


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


def test_lexical_join_checks_source_and_requires_complete_unique_sample() -> None:
    sample = select([_article(volume, 0) for volume in (2, 3, 4)], per_volume=1)
    lexical = [{"article_id": row["article_id"],
                "source_faithful_sha256": row["source_faithful_sha256"],
                "visual_sha256": row["visual_sha256"],
                "definitions": [{"visual_start": 3, "visual_end": 7}],
                "tibetan_examples": [{"visual_start": 3, "visual_end": 7,
                                        "lexical_region": True}],
                "belegstellen": []} for row in sample]
    joined = with_lexical_predictions(sample, lexical)
    assert joined[0]["predictions"]["definition"] == [(3, 7)]
    assert joined[0]["predictions"]["tibetan_example"] == []
    with pytest.raises(ValueError, match="duplicate lexical article_id"):
        with_lexical_predictions(sample, lexical + lexical[:1])
    with pytest.raises(ValueError, match="missing lexical candidates"):
        with_lexical_predictions(sample, lexical[:-1])
    with pytest.raises(ValueError, match="lexical source mismatch"):
        with_lexical_predictions(sample, lexical[:1] + [dict(lexical[1], visual_sha256="0" * 64)]
                                 + lexical[2:])


def test_prediction_refresh_preserves_frozen_review_identity() -> None:
    articles = [_article(volume, 0) for volume in (2, 3, 4)]
    sample = select(articles, per_volume=1)
    sample[0]["predictions"]["numbered_sense"] = [(0, 1)]
    refreshed = refresh_predictions(sample, reversed(articles))
    assert refreshed[0]["predictions"]["numbered_sense"] == [(0, 2)]
    assert refreshed[0]["source_faithful_sha256"] == articles[0]["source_faithful_sha256"]
    with pytest.raises(ValueError, match="duplicate source article_id"):
        refresh_predictions(sample, articles + articles[:1])
    with pytest.raises(ValueError, match="missing structural sources"):
        refresh_predictions(sample, articles[:-1])
    corrupt = [dict(articles[0], source_faithful_sha256="0" * 64)] + articles[1:]
    with pytest.raises(ValueError, match="sample source mismatch"):
        refresh_predictions(sample, corrupt)


def test_windowed_review_scores_later_article_spans_and_rejects_gap_annotations() -> None:
    articles = [_article(volume, 0) for volume in (2, 3, 4)]
    for article in articles:
        article["visual_lines"] = [{"text": "1. Wort"}, {"text": "unreviewed middle"},
                                   {"text": "later „meaning“ (Mil 74,4)"}]
        text = "\n".join(line["text"] for line in article["visual_lines"])
        quote_start = text.index("„meaning“")
        article["candidates"]["german_quotes"] = [{"visual_start": quote_start,
                                                      "visual_end": quote_start + len("„meaning“")}]
        article["candidates"]["parenthetical_citations"] = []
        article["candidates"]["cross_references"] = []
        article["source_faithful_sha256"] = sha256(text.encode()).hexdigest()
    sample = select(articles, per_volume=1, review_chars=7, windowed=True)
    row = sample[0]
    assert row["contract_version"].endswith("v2")
    assert len(row["reviewed_ranges"]) == 2
    later = row["visual_text"].index("„meaning“")
    assert row["reviewed_ranges"][1][0] <= later
    marker = {"sample_index": "0", "article_id": row["article_id"],
              "kind": "reviewed", "text": "german_quote", "occurrence": ""}
    annotation = dict(marker, kind="german_quote", text="„meaning“")
    gold = materialize_gold([row], [marker, annotation])
    assert gold[0]["spans"][0]["start"] == later
    assert score([row], gold)["metrics"]["german_quote"]["gold"] == 1
    with pytest.raises(ValueError, match="absent/occurrence"):
        materialize_gold([row], [marker, dict(annotation, text="unreviewed")])
    corrupt = [dict(gold[0], reviewed_ranges=[[0, 7]])]
    with pytest.raises(ValueError, match="source/review boundary"):
        score([row], corrupt)


def test_windowed_lexical_join_and_refresh_leave_input_untouched() -> None:
    articles = [_article(volume, 0) for volume in (2, 3, 4)]
    sample = select(articles, per_volume=1, windowed=True)
    lexical = [{"article_id": row["article_id"],
                "source_faithful_sha256": row["source_faithful_sha256"],
                "visual_sha256": row["visual_sha256"],
                "definitions": [{"visual_start": 3, "visual_end": 7}],
                "tibetan_examples": [], "belegstellen": []} for row in sample]
    joined = with_lexical_predictions(sample, lexical)
    assert joined[0]["predictions"]["definition"] == [(3, 7)]
    assert sample[0]["predictions"]["definition"] == []
    joined[0]["predictions"]["numbered_sense"] = []
    refreshed = refresh_predictions(joined, articles)
    assert refreshed[0]["predictions"]["numbered_sense"] == [(0, 2)]
    assert joined[0]["predictions"]["numbered_sense"] == []


def test_windowed_review_assignments_are_frozen_and_input_order_independent() -> None:
    articles = [_article(volume, suffix) for volume in (2, 3, 4) for suffix in range(45)]
    first = select(articles, per_volume=40, windowed=True)
    assert first == select(reversed(articles), per_volume=40, windowed=True)
    for volume in (2, 3, 4):
        rows = [row for row in first if row["volume"] == volume]
        assert len(rows) == 40
        assert sum(row["review_partition"] == "development" for row in rows) == 30
        assert sum(row["review_partition"] == "acceptance" for row in rows) == 10
        assert sum(row["double_review"] for row in rows) == 6


def test_correction_stratum_reviews_literal_apparatus_and_joins_predictions() -> None:
    articles = [_article(volume, suffix) for volume in (2, 3, 4) for suffix in range(12)]
    for article in articles:
        text = "opening line\n" + "middle\n" * 100 + "blta (r. lta) „sah“ (Mil 1)"
        article["visual_lines"] = [{"text": line} for line in text.split("\n")]
        article["divisions"] = []
        article["candidates"] = {"german_quotes": [], "parenthetical_citations": [],
                                 "cross_references": [], "adjacent_quote_citation_pairs": []}
        article["source_faithful_sha256"] = sha256(text.encode()).hexdigest()
    sample = select(articles, per_volume=9, review_chars=40, windowed=True)
    correction_rows = [row for row in sample if row["stratum"] == "correction"]
    assert correction_rows
    for row in correction_rows:
        start = row["visual_text"].index("(r. lta)")
        assert any(left <= start and start + 8 <= right
                   for left, right in row["reviewed_ranges"])
    lexical = [{"article_id": row["article_id"],
                "source_faithful_sha256": row["source_faithful_sha256"],
                "visual_sha256": row["visual_sha256"],
                "definitions": [], "tibetan_examples": [], "belegstellen": [],
                "correction_apparatus": [{"visual_start": row["visual_text"].index("(r. lta)"),
                                          "visual_end": row["visual_text"].index("(r. lta)") + 8}]}
               for row in sample]
    joined = with_lexical_predictions(sample, lexical)
    correction_ids = {row["article_id"] for row in correction_rows}
    assert all(row["predictions"]["correction_apparatus"] for row in joined
               if row["article_id"] in correction_ids)
