"""Small synthetic externally evidenced publications; no live network."""
import csv
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from badw_bibliography_external import load_publications
from badw_bibliography import export_bibtex, AuthorityResolver
from badw_bibliography_aliases import load_reviews


def fixture(tmp_path, **changes):
    body = b"synthetic publisher title page"
    digest = hashlib.sha256(body).hexdigest()
    obj = tmp_path / "objects" / "sha256" / digest[:2] / digest
    obj.parent.mkdir(parents=True)
    obj.write_bytes(body)
    row = dict(key="author-2005", label="Author 2005", year="2005", author="Author",
        title="Synthetic title", publisher="Publisher", source_url="https://example.org/title.pdf",
        source_sha256=digest, evidence_note="Reviewed synthetic cover")
    row.update(changes)
    path = tmp_path / "publications.tsv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=row, delimiter="\t")
        writer.writeheader()
        writer.writerow(row)
    return path, obj


def test_reproducible_external_contract_and_bibtex(tmp_path):
    path, _ = fixture(tmp_path)
    rows = load_publications(path, tmp_path)
    assert rows == load_publications(path, tmp_path)
    assert rows[0]["scope"] == "reviewed_external"
    assert "not a WTS bibliography row" in export_bibtex(rows)
    assert "Synthetic title" in export_bibtex(rows)
    assert load_publications(None, tmp_path) == []


@pytest.mark.parametrize("changes,message", [
    ({"year": "200"}, "invalid year"), ({"source_url": "http://example.org"}, "HTTPS"),
    ({"source_sha256": "f"*64}, "object/hash"), ({"evidence_note": ""}, "metadata/evidence")])
def test_external_evidence_gates(tmp_path, changes, message):
    path, _ = fixture(tmp_path, **changes)
    with pytest.raises(ValueError, match=message):
        load_publications(path, tmp_path)


def test_corrupt_external_object_rejected(tmp_path):
    path, obj = fixture(tmp_path)
    obj.write_bytes(b"changed")
    with pytest.raises(ValueError, match="object/hash"):
        load_publications(path, tmp_path)


def test_external_identity_is_never_an_automatic_author_year_match(tmp_path):
    path, _ = fixture(tmp_path)
    rows = load_publications(path, tmp_path)
    authorities = [{k: r[k] for k in ("id", "kind", "label", "scope", "status")} for r in rows]
    resolver = AuthorityResolver(authorities, rows)
    assert resolver.resolve("(Author 2005: 46)", "pdf")["status"] == "unmatched"


def test_duplicate_keys_rejected(tmp_path):
    path, _ = fixture(tmp_path)
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines + [lines[1]]) + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_publications(path, tmp_path)


def test_reviewed_work_alias_preserves_source_and_does_not_assert_edition(tmp_path):
    path, obj = fixture(tmp_path, kind="work", year="", publisher="", label="BDSN")
    digest = obj.name
    text = path.read_text().replace("https://example.org/title.pdf", "urn:sha256:" + digest)
    path.write_text(text)
    rows = load_publications(path, tmp_path)
    row = rows[0]
    registry = tmp_path / "sources.tsv"
    registry.write_text("sha256\tlabel\n")
    review = dict(layer="html", alias="Mim1", canonical_label="BDSN",
        online_occurrence_id=row["occurrence_id"], online_source_sha256=digest,
        print_pdf_sha256=digest, print_scan_page="1",
        status="visually_reviewed_work_identity", evidence_note="Independent numbered pairs")
    reviews = tmp_path / "aliases.tsv"

    def write():
        with reviews.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=review, delimiter="\t")
            writer.writeheader()
            writer.writerow(review)

    authorities = [{k: row[k] for k in ("id", "kind", "label", "scope", "status")}]
    assert AuthorityResolver(authorities, rows).resolve("BDSN 51", "html")["status"] == "unmatched"
    for layer in ("html", "pdf"):
        review["layer"] = layer
        write()
        aliases = load_reviews(reviews, rows, registry, tmp_path)
        result = AuthorityResolver(authorities, rows, aliases).resolve("(Mim1 51)", layer)
        assert result["text"] == "(Mim1 51)"
        assert result["status"] == "exact_external_work_rows"
        assert result["matches"][0]["authority_ids"] == [row["id"]]
        assert result["matches"][0]["edition_status"] == "unreviewed"
    obj.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="review evidence"):
        load_reviews(reviews, rows, registry, tmp_path)
