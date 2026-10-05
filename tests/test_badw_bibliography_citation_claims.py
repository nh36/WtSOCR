"""Separate identity/edition/locator claims with synthetic evidence only."""
import copy
import csv
import hashlib
from pathlib import Path
import sys

import pytest
from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from badw_bibliography_citation_claims import CitationClaims


def setup(tmp_path, **changes):
    pdf = tmp_path / "evidence.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(pdf)
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    obj = tmp_path / "objects" / "sha256" / digest[:2] / digest
    obj.parent.mkdir(parents=True, exist_ok=True)
    obj.write_bytes(pdf.read_bytes())
    row = dict(layer="pdf", citation_id="c1", text_sha256=hashlib.sha256(b"(Author 1992: 42)").hexdigest(),
               claim="locator", status="corroborated_in_other_edition", witness_authority_id="p1",
               literal_locator="42", evidence_sha256=digest, evidence_pdf_page="1",
               witness_printed_page="42", evidence_note="Synthetic fixture, not a scholarly review")
    row.update(changes)
    path = tmp_path / "claims.tsv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        out = csv.DictWriter(stream, fieldnames=row, delimiter="\t")
        out.writeheader()
        out.writerow(row)
    return CitationClaims(path, tmp_path), obj


def result():
    return dict(text="(Author 1992: 42)", status="reviewed_work_candidate", matches=[dict(
        authority_ids=["p1"], method="exact_citation_source_review",
        edition_status="year_discrepancy_unresolved", locator_status="unreviewed")])


def test_claim_does_not_accept_an_edition_or_change_source(tmp_path):
    claims, _ = setup(tmp_path)
    original = result()
    linked = claims.apply("pdf", "c1", copy.deepcopy(original))
    assert linked["matches"] == original["matches"]
    assert linked["text"] == original["text"] and linked["status"] == original["status"]
    assert linked["reviewed_claims"][0]["status"] == "corroborated_in_other_edition"
    claims.finish()


@pytest.mark.parametrize("changes,message", [
    ({"evidence_sha256": "a" * 64}, "object/hash"),
    ({"evidence_pdf_page": "2"}, "outside PDF"),
    ({"evidence_pdf_page": "0"}, "outside PDF"),
    ({"text_sha256": "z" * 64}, "invalid claim hash"),
    ({"status": "verified_cited_edition"}, "unsupported"),
    ({"evidence_note": ""}, "lacks evidence"),
])
def test_invalid_claim_rejected(tmp_path, changes, message):
    with pytest.raises(ValueError, match=message):
        setup(tmp_path, **changes)


def test_stale_orphan_and_unreviewed_target_rejected(tmp_path):
    claims, _ = setup(tmp_path)
    with pytest.raises(ValueError, match="orphan"):
        claims.finish()
    for field, value, message in (("text", "changed", "stale"), ("matches", [], "unique")):
        source = result()
        source[field] = value
        with pytest.raises(ValueError, match=message):
            claims.apply("pdf", "c1", source)
    source = result()
    source["matches"][0]["edition_status"] = "verified"
    with pytest.raises(ValueError, match="unresolved cited edition"):
        claims.apply("pdf", "c1", source)


def test_locator_must_not_match_substring(tmp_path):
    claims, _ = setup(tmp_path, literal_locator="4")
    with pytest.raises(ValueError, match="locator absent"):
        claims.apply("pdf", "c1", result())


def test_work_identity_is_separate_claim(tmp_path):
    claims, _ = setup(tmp_path, claim="work_identity", status="reviewed_work_identity")
    linked = claims.apply("pdf", "c1", result())
    assert linked["status"] == "reviewed_work_candidate"
    assert linked["reviewed_claims"][0]["claim"] == "work_identity"
    claims.finish()


def year_claim(tmp_path, **changes):
    return setup(tmp_path, claim="citation_year", status="reviewed_year_correction",
                 evidence_sha256="", evidence_pdf_page="", witness_printed_page="",
                 evidence_kind="author_confirmation_reported_by_user",
                 evidence_reported_date="2026-10-05", corrected_year="1996", **changes)[0]


def test_author_confirmation_accepts_identity_not_locator_or_source_rewrite(tmp_path):
    from badw_bibliography import AuthorityResolver
    claims = year_claim(tmp_path)
    source = result()
    source["matches"][0].update(status="reviewed_work_candidate",
        start=1, end=12,
        publication_year_relation=dict(literal_year="1992", target_year="1996"))
    linked = claims.apply("pdf", "c1", source)
    AuthorityResolver.component_contract(linked)
    match = linked["matches"][0]
    assert linked["text"] == "(Author 1992: 42)"
    assert match["target_status"] == "accepted_identity"
    assert match["locator_status"] == "unreviewed"
    assert match["publication_year_relation"]["literal_year"] == "1992"
    assert match["publication_year_relation"]["status"] == "reviewed_year_correction"
    claims.finish()


@pytest.mark.parametrize("field,value,message", [
    ("evidence_reported_date", "yesterday", "ISO reported date"),
    ("evidence_kind", "unspecified", "provenance"),
    ("corrected_year", "unknown", "invalid author-confirmed"),
    ("evidence_sha256", "a" * 64, "invalid author-confirmed"),
])
def test_year_assertion_requires_explicit_provenance(tmp_path, field, value, message):
    options = dict(claim="citation_year", status="reviewed_year_correction",
        evidence_sha256="", evidence_pdf_page="", witness_printed_page="",
        evidence_kind="author_confirmation_reported_by_user",
        evidence_reported_date="2026-10-05", corrected_year="1996")
    options[field] = value
    with pytest.raises(ValueError, match=message):
        setup(tmp_path, **options)


def test_year_claim_rejects_wrong_publication(tmp_path):
    claims = year_claim(tmp_path)
    source = result()
    source["matches"][0].update(status="reviewed_work_candidate",
        publication_year_relation=dict(literal_year="1992", target_year="2001"))
    with pytest.raises(ValueError, match="differing-year"):
        claims.apply("pdf", "c1", source)
