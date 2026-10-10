"""Synthetic exact-citation evidence gates; no downloaded source fixtures."""
import csv
import hashlib
from pathlib import Path
import sys
import sqlite3

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from badw_bibliography_citation_reviews import CitationReviews


def test_supplemental_citation_is_exact_hash_bound_source_span(tmp_path):
    text = "prefix (Author 1992: 4) suffix"
    literal = "(Author 1992: 4)"
    start, end = 7, 7 + len(literal)
    identity = f"article:reviewed:{start}:{end}"
    reviews, _ = setup_review(tmp_path, citation_id=identity,
        source_article_id="article", source_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source_start=str(start), source_end=str(end))
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE pdf_article_witness (id TEXT, source_faithful_text TEXT)")
    db.execute("INSERT INTO pdf_article_witness VALUES (?,?)", ("article", text))
    assert list(reviews.supplemental_citations(db)) == [(identity, literal)]
    reviews.apply("pdf", identity, result())
    reviews.finish()
    db.execute("UPDATE pdf_article_witness SET source_faithful_text='changed'")
    with pytest.raises(ValueError, match="hash"):
        list(reviews.supplemental_citations(db))
    db.close()


def setup_review(tmp_path, printed=None, **changes):
    body = b"synthetic visible source"
    digest = hashlib.sha256(body).hexdigest()
    obj = tmp_path / "objects" / "sha256" / digest[:2] / digest
    obj.parent.mkdir(parents=True, exist_ok=True)
    obj.write_bytes(body)
    row = dict(layer="pdf", citation_id="c1", text_sha256=hashlib.sha256(b"(Author 1992: 4)").hexdigest(),
        status="reviewed_identity", start="1", end="12", online_occurrence_id="o1",
        online_source_sha256="a" * 64, evidence_sha256=digest, evidence_page="1", evidence_note="visible identity only")
    row.update(changes)
    path = tmp_path / "reviews.tsv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=row, delimiter="\t")
        writer.writeheader()
        writer.writerow(row)
    targets = [dict(occurrence_id="o1", source_sha256="a" * 64, kind="publication", id="p1",
                    year="1996", scope="reviewed_external" if row["status"] == "reviewed_external_identity" else "badw_online")]
    return CitationReviews(path, targets, tmp_path, None, printed), obj


@pytest.mark.parametrize('changes', [
    dict(source_start='0'), dict(source_article_id='article'),
    dict(source_article_id='article', source_text_sha256='z' * 64, source_start='0', source_end='2'),
])
def test_partial_source_span_binding_fails_closed(tmp_path, changes):
    with pytest.raises(ValueError, match='source-span binding'):
        setup_review(tmp_path, **changes)


def result():
    return dict(text="(Author 1992: 4)", status="unmatched", matches=[])


def test_html_review_requires_exact_article_view_and_span(tmp_path):
    text = "prefix (Author 1992: 4) suffix"
    start, end = 7, 7 + len(result()["text"])
    reviews, _ = setup_review(tmp_path, layer="html",
        citation_id=f"article:reviewed:{start}:{end}", source_article_id="article",
        source_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source_start=str(start), source_end=str(end))
    for changed in ("changed " + text, text.replace("suffix", "altered")):
        with pytest.raises(ValueError, match="article/span/hash"):
            reviews.apply_source("html", "article", changed, start, end, result())
    assert reviews.apply_source("html", "other", text, start, end, result())["matches"] == []
    with pytest.raises(ValueError, match="orphan"):
        reviews.finish()
    linked = reviews.apply_source("html", "article", text, start, end, result())
    assert linked["matches"][0]["authority_ids"] == ["p1"]
    assert linked["text"] == text[start:end]
    assert linked["matches"][0]["locator_status"] == "unreviewed"
    reviews.finish()


def test_html_review_without_source_binding_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="requires exact source-span"):
        setup_review(tmp_path, layer="html")


def test_exact_identity_preserves_text_and_never_certifies_edition(tmp_path):
    reviews, obj = setup_review(tmp_path)
    linked = reviews.apply("pdf", "c1", result())
    assert linked["text"] == result()["text"]
    assert linked["matches"][0]["label"] == "Author 1992"
    assert linked["matches"][0]["edition_status"] == "unreviewed"
    assert linked["matches"][0]["authority_ids"] == ["p1"]
    reviews.finish()


def test_print_only_identity_is_distinct_and_hash_pinned(tmp_path):
    printed = [dict(id="print1", authority_id="old-edition", candidate=dict(pdf_sha256="b" * 64))]
    changes = dict(status="reviewed_print_identity", online_occurrence_id="", online_source_sha256="",
                   print_occurrence_id="print1", print_source_sha256="b" * 64)
    reviews, _ = setup_review(tmp_path, printed=printed, **changes)
    linked = reviews.apply("pdf", "c1", result())
    assert linked["status"] == "exact_print_publication_rows"
    match = linked["matches"][0]
    assert match["authority_ids"] == ["old-edition"]
    assert match["edition_status"] == match["locator_status"] == "unreviewed"
    assert match["literal_years"] == ["1992"]
    reviews.finish()
    for change in ({"print_source_sha256": "c" * 64}, {"print_occurrence_id": "missing"},
                   {"online_occurrence_id": "o1"}):
        with pytest.raises(ValueError, match="print target"):
            setup_review(tmp_path, printed=printed, **{**changes, **change})


@pytest.mark.parametrize("changes,message", [
    ({"text_sha256": "z" * 64}, "source hash"),
    ({"evidence_sha256": "a" * 64}, "object/hash"),
    ({"evidence_page": "0"}, "positive page"),
    ({"online_source_sha256": "b" * 64}, "target occurrence"),
    ({"online_occurrence_id": "absent"}, "target occurrence"),
    ({"print_occurrence_id": "print1"}, "must not supply a print target"),
    ({"status": "guessed"}, "unsupported"),
])
def test_invalid_evidence_rejected(tmp_path, changes, message):
    with pytest.raises(ValueError, match=message):
        setup_review(tmp_path, **changes)


def test_stale_source_span_and_orphan_reviews_rejected(tmp_path):
    reviews, _ = setup_review(tmp_path, end="200")
    with pytest.raises(ValueError, match="orphan"):
        reviews.finish()
    with pytest.raises(ValueError, match="outside source"):
        reviews.apply("pdf", "c1", result())
    with pytest.raises(ValueError, match="stale"):
        reviews.apply("pdf", "c1", dict(text="changed", matches=[]))


def test_unresolved_disposition_is_not_an_edge(tmp_path):
    reviews, _ = setup_review(tmp_path, status="unresolved_publication_or_edition",
        start="", end="", online_occurrence_id="", online_source_sha256="")
    linked = reviews.apply("pdf", "c1", result())
    assert linked["matches"] == [] and linked["status"] == "unmatched"
    assert linked["citation_review"]["status"] == "unresolved_publication_or_edition"
    reviews.finish()


def test_work_candidate_preserves_year_and_is_not_accepted(tmp_path):
    from badw_bibliography import AuthorityResolver
    reviews, _ = setup_review(tmp_path, status="reviewed_work_candidate")
    linked = reviews.apply("pdf", "c1", result())
    AuthorityResolver.component_contract(linked)
    match = linked["matches"][0]
    assert match["target_status"] == "candidate"
    assert match["publication_year_relation"] == dict(literal_year="1992", target_year="1996",
        status="reviewed_candidate_not_a_year_correction")
    assert match["edition_status"] == "year_discrepancy_unresolved"
    assert linked["edition_status"] == "year_discrepancy_unresolved"
    assert linked["residual_reason"] == "reviewed_work_candidate_requires_cited_edition_evidence"
    assert linked["text"] == result()["text"]
    reviews.finish()


def test_candidate_requires_differing_year_in_exact_span(tmp_path):
    reviews, _ = setup_review(tmp_path, status="reviewed_work_candidate", end="7")
    with pytest.raises(ValueError, match="differing citation year"):
        reviews.apply("pdf", "c1", result())


def test_candidate_cannot_claim_a_same_year_discrepancy(tmp_path):
    text = "(Author 1996: 4)"
    reviews, _ = setup_review(tmp_path, status="reviewed_work_candidate",
        text_sha256=hashlib.sha256(text.encode()).hexdigest())
    with pytest.raises(ValueError, match="differing citation year"):
        reviews.apply("pdf", "c1", dict(text=text, matches=[]))


def test_external_identity_is_accepted_without_edition_or_locator_claim(tmp_path):
    from badw_bibliography import AuthorityResolver
    reviews, _ = setup_review(tmp_path, status="reviewed_external_identity")
    linked = reviews.apply("pdf", "c1", result())
    AuthorityResolver.component_contract(linked)
    match = linked["matches"][0]
    assert match["target_status"] == "accepted_identity"
    assert match["edition_status"] == match["locator_status"] == "unreviewed"
    assert linked["status"] == "exact_external_publication_rows"


def test_existing_candidate_cannot_be_promoted_by_exact_review(tmp_path):
    reviews, _ = setup_review(tmp_path)
    value = result()
    value["matches"] = [dict(start=1, end=3, status="candidate")]
    with pytest.raises(ValueError, match="unmatched"):
        reviews.apply("pdf", "c1", value)


def test_unknown_marker_is_preserved_and_cannot_be_bisected(tmp_path):
    text = "(D⟦UNKNOWN:Font:regular:009F:abc⟧VILLE 1952: 10)"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    reviews, _ = setup_review(tmp_path, text_sha256=digest, end="14")
    with pytest.raises(ValueError, match="bisects"):
        reviews.apply("pdf", "c1", dict(text=text, matches=[]))
    reviews, _ = setup_review(tmp_path, text_sha256=digest, end=str(text.rfind(":")))
    linked = reviews.apply("pdf", "c1", dict(text=text, matches=[]))
    assert linked["text"] == text
    assert linked["matches"][0]["label"] == text[1:text.rfind(":")]
