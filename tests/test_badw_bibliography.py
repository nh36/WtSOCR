"""Tiny synthetic source rows; no downloaded bibliography fixtures."""
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import badw_bibliography as bib


def parse(html, kind="work", url="https://example.test/texte"):
    body = html.encode("utf-8")
    return bib.parse_page(body, {"sha256": bib.digest(body), "http_status": 200,
        "requested_url": url, "final_url": url, "fetched_at_utc": "2026-01-01T00:00:00Z",
        "response_headers": {"content-type": "text/html; charset=utf-8"}}, kind)


WORK = '''<table><tr><td class="textsiglum">PW</td><td class="textallg">ś &amp; ṅ:
<i>Title</i>. <span class="bibl info"><sc>Author</sc> <j>2001</j><span class="infotext">
HIDDEN <span class="bibl"><sc>Wrong</sc><j>1900</j></span></span></span>.
<span hidden="hidden">SECRET</span><span aria-hidden="true">UI</span></td></tr></table>'''
PUBLICATION = '''<table><tr><td class="autor_jahr"><sc>Author</sc>, A. 2001</td>
<td class="titel_etc"><i>Title &amp; subtitle</i>. Press. [<span class="textsiglum">PW</span>]</td></tr></table>'''
ABBREVIATION = '''<div class="content"><table><tr><td>Ed.</td><td>Edition</td></tr></table></div>'''


def test_unicode_visible_nodes_and_provenance():
    row = parse(WORK)[0]
    assert row["text"].startswith("ś & ṅ:\nTitle")
    assert all(s not in row["text"] for s in ("HIDDEN", "SECRET", "UI", "Wrong"))
    assert "".join(n["text"] for n in row["text_nodes"]) == row["text"]
    for node in row["text_nodes"]:
        assert row["text"][node["start"]:node["end"]] == node["text"]
        assert node["dom_path"] and node["source_line"] >= 1
    assert row["publication_references"][0]["key"] == "Author 2001"
    assert len(row["publication_references"]) == 1
    assert parse(WORK) == parse(WORK)


def test_identity_survives_description_changes_but_observation_does_not():
    old, new = parse(WORK)[0], parse(WORK.replace("Title", "Revised"))[0]
    assert old["id"] == new["id"]
    assert old["occurrence_id"] != new["occurrence_id"]
    assert old["source_sha256"] != new["source_sha256"]


def test_work_publication_relations_and_ambiguous_editions():
    works = parse(WORK)
    publications = parse(PUBLICATION, "publication")
    authorities, relations = bib.authority_graph(works + publications)
    assert {a["kind"] for a in authorities} == {"work", "publication"}
    assert relations[0]["status"] == "exact_reference_candidate"
    assert relations[0]["relation_kind"] == "edition_or_containment_unreviewed"
    assert publications[0]["associated_sigla"] == ["PW"]
    second = parse(PUBLICATION.replace("A. 2001", "B. 2001"), "publication")
    assert bib.authority_graph(works + publications + second)[1][0]["status"] == "ambiguous"
    assert bib.authority_graph(works)[1][0]["status"] == "unmatched"


def test_untagged_reference_year_and_open_publication_range():
    works = parse(WORK.replace("<j>2001</j>", "2001 ff."))
    publications = parse(PUBLICATION.replace("2001", "2001 ff."), "publication")
    assert works[0]["publication_references"][0]["key"] == "Author 2001 ff."
    assert publications[0]["reference_key"] == "Author 2001 ff."
    assert bib.authority_graph(works + publications)[1][0]["status"] == "exact_reference_candidate"
    noisy = parse(WORK.replace("<j>2001</j>", "2001 and unidentified 2002"))
    assert noisy[0]["publication_references"][0]["key"] is None


def test_case_overlap_conflicting_descriptions_and_offsets():
    rows = parse(WORK) + parse(WORK.replace("PW", "pw"))
    resolver = bib.AuthorityResolver(bib.authority_graph(rows)[0])
    for label in ("PW", "pw"):
        result = resolver.resolve("(" + label + "12, 3)")
        assert result["status"] == "exact_online_work_rows"
        assert result["matches"][0]["label"] == label
        assert result["matches"][0]["edition_status"] == "unreviewed"
    assert resolver.resolve("Pw 3")["status"] == "unmatched"
    assert resolver.resolve("xPW 3")["status"] == "unmatched"
    conflict = bib.AuthorityResolver(bib.authority_graph(rows + parse(WORK.replace("Title", "Other")))[0])
    assert conflict.resolve("PW 3")["status"] == "ambiguous"
    overlap = parse(WORK.replace("PW", "Dol")) + parse(WORK.replace("PW", "Dol4"))
    assert bib.AuthorityResolver(bib.authority_graph(overlap)[0]).resolve("Dol4 3")["status"] == "ambiguous"


def test_bibtex_is_partial_not_invented_metadata():
    rows = parse(WORK) + parse(PUBLICATION, "publication")
    text = bib.export_bibtex(rows)
    assert text == bib.export_bibtex(list(reversed(rows)))
    assert "@misc{" in text and "Partial source record" in text
    assert "  author =" not in text and "  title =" not in text
    assert "ś" in text and r"\&" in text
    assert bib.bibtex_escape("{%_\\}") == r"\{\%\_{\textbackslash}\}"


def test_invalid_source_and_abbreviation_scope():
    body = WORK.encode()
    with pytest.raises(ValueError, match="hash/status"):
        bib.parse_page(body, {"sha256": "wrong", "http_status": 200}, "work")
    with pytest.raises(ValueError, match="no recognized"):
        parse("<table><tr><td>Ed.</td><td>Edition</td></tr></table>", "abbreviation")
    assert parse(ABBREVIATION, "abbreviation")[0]["label"] == "Ed."


def test_print_inventory_fascicle_supplements_are_candidates(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"synthetic registered print")
    pdf.with_suffix(".vision.txt").write_text(
        "=== page 001 ===\nMit Lieferung 31 hinzugekommene Quellentexte, Literatur und Abkürzungen\n"
        "=== page 002 ===\n2. Literaturverzeichnis\n", encoding="utf-8")
    registry = tmp_path / "sources.tsv"
    registry.write_text("label\tfilename\tsha256\nscan\t" + str(pdf) + "\t" + bib.file_digest(pdf) + "\n")
    rows = bib.print_inventory(registry)
    assert [r["scan_page"] for r in rows] == [1, 2]
    assert all(r["status"] == "heading_candidate_requires_print_review" for r in rows)
    assert all(r["pdf_sha256"] == bib.file_digest(pdf) for r in rows)


def test_offline_build_fk_links_and_reproducibility(tmp_path, monkeypatch):
    bodies = {"texte": WORK, "bibliographie": PUBLICATION, "abkuerzungen": ABBREVIATION}
    calls = []

    class Cache:
        def __init__(self, root):
            pass

        def fetch(self, request, *, offline):
            assert offline is True
            calls.append(request.url)
            body = bodies[request.url.rsplit("/", 1)[-1]].encode()
            return SimpleNamespace(body=body, metadata={"sha256": bib.digest(body),
                "http_status": 200, "requested_url": request.url, "final_url": request.url,
                "fetched_at_utc": "2026-01-01T00:00:00Z"})

    monkeypatch.setattr(bib, "SourceCache", Cache)
    staging = tmp_path / "staging.sqlite"
    with sqlite3.connect(staging) as db:
        db.executescript("CREATE TABLE citation(id,raw_text); INSERT INTO citation VALUES('h','PW12');"
            "CREATE TABLE pdf_lexical_candidate(article_id,kind,ordinal,text);"
            "INSERT INTO pdf_lexical_candidate VALUES('p','citation',1,'unknown');")
    schema = Path(__file__).resolve().parents[1] / "data/bibliography_database.schema.sql"
    first, second = tmp_path / "work/first", tmp_path / "work/second"
    summary = bib.build(tmp_path, first, schema, staging)
    assert summary == bib.build(tmp_path, second, schema, staging)
    assert summary["citation_statuses"] == {"html:exact_online_work_rows": 1, "pdf:unmatched": 1}
    assert len(calls) == 6
    for filename in ("source_rows.jsonl", "relations.jsonl", "citation_links.jsonl", "citation_review_queue.jsonl", "sources.bib", "manifest.json"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()
    assert '"citation_id":"p:1"' in (first / "citation_review_queue.jsonl").read_text()
    assert '"citation_id":"h"' not in (first / "citation_review_queue.jsonl").read_text()
    with sqlite3.connect(first / "bibliography.sqlite") as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT COUNT(*) FROM citation_target").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM authority").fetchone()[0] == 3
    with pytest.raises(ValueError, match="immutable"):
        bib.build(tmp_path, first, schema)
    with pytest.raises(ValueError, match="under work"):
        bib.build(tmp_path, tmp_path / "outside", schema)
