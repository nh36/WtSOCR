"""Synthetic exact-citation evidence gates; no downloaded source fixtures."""
import csv
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from badw_bibliography_citation_reviews import CitationReviews


def setup_review(tmp_path, **changes):
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
    targets = [dict(occurrence_id="o1", source_sha256="a" * 64, kind="publication", id="p1")]
    return CitationReviews(path, targets, tmp_path, None), obj


def result():
    return dict(text="(Author 1992: 4)", status="unmatched", matches=[])


def test_exact_identity_preserves_text_and_never_certifies_edition(tmp_path):
    reviews, obj = setup_review(tmp_path)
    linked = reviews.apply("pdf", "c1", result())
    assert linked["text"] == result()["text"]
    assert linked["matches"][0]["label"] == "Author 1992"
    assert linked["matches"][0]["edition_status"] == "unreviewed"
    assert linked["matches"][0]["authority_ids"] == ["p1"]
    reviews.finish()


@pytest.mark.parametrize("changes,message", [
    ({"text_sha256": "z" * 64}, "source hash"),
    ({"evidence_sha256": "a" * 64}, "object/hash"),
    ({"evidence_page": "0"}, "positive page"),
    ({"online_source_sha256": "b" * 64}, "target occurrence"),
    ({"online_occurrence_id": "absent"}, "target occurrence"),
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
