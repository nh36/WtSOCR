"""Tiny synthetic source rows; no downloaded bibliography fixtures."""
from pathlib import Path
import sqlite3
import csv
import json
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import badw_bibliography as bib
from badw_bibliography_aliases import load_reviews


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


def test_reviewed_alias_is_layer_bounded_and_source_preserving(tmp_path):
    rows = parse(WORK.replace("PW", "HṚ"))
    row = rows[0]
    registry = tmp_path / "registry.tsv"
    registry.write_text("sha256\tlabel\nprint-hash\tprint\n")
    review = dict(layer="pdf", alias="HR", canonical_label="HṚ",
                  online_occurrence_id=row["occurrence_id"],
                  online_source_sha256=row["source_sha256"], print_pdf_sha256="print-hash",
                  print_scan_page="1", status="visually_reviewed_work_identity", evidence_note="Review")
    path = tmp_path / "reviews.tsv"

    def write():
        with path.open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(review), delimiter="\t")
            writer.writeheader()
            writer.writerow(review)

    write()
    aliases = load_reviews(path, rows, registry)
    resolver = bib.AuthorityResolver(bib.authority_graph(rows)[0], rows, aliases)
    text = "(HR 56,19)"
    result = resolver.resolve(text, "pdf")
    assert result["status"] == "exact_online_work_rows"
    assert result["text"] == text and result["matches"][0]["raw_text"] == "HR"
    assert result["matches"][0]["edition_status"] == "unreviewed"
    assert result["unparsed_spans"][1]["raw_text"] == " 56,19)"
    for text, layer in (("HR 2", "html"), ("HR-other 2", "pdf"), ("xHR 2", "pdf")):
        assert resolver.resolve(text, layer)["status"] == "unmatched"
    for field, value in (("online_source_sha256", "stale"), ("canonical_label", "wrong"),
                         ("print_scan_page", "0"), ("print_pdf_sha256", "unknown"),
                         ("status", "candidate"), ("layer", "html"), ("evidence_note", "")):
        original = review[field]
        review[field] = value
        write()
        with pytest.raises(ValueError):
            load_reviews(path, rows, registry)
        review[field] = original


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
    result = bib.AuthorityResolver(bib.authority_graph(overlap)[0]).resolve("Dol4 3")
    assert result["status"] == "exact_online_work_rows"
    assert result["matches"][0]["canonical_label"] == "Dol4"


def test_bibtex_is_partial_not_invented_metadata():
    rows = parse(WORK) + parse(PUBLICATION, "publication")
    text = bib.export_bibtex(rows)
    assert text == bib.export_bibtex(list(reversed(rows)))
    assert "@misc{" in text and "Partial source record" in text
    assert "  author =" not in text and "  title =" not in text
    assert "ś" in text and r"\&" in text
    assert bib.bibtex_escape("{%_\\}") == r"\{\%\_{\textbackslash}\}"


def test_split_author_and_exact_publication_preserve_raw_spans():
    rows = parse(WORK.replace("PW", "K")) + parse(PUBLICATION, "publication")
    resolver = bib.AuthorityResolver(bib.authority_graph(rows)[0], rows)
    result = resolver.resolve("K\nRETSCHMAR 1981, p. 4")
    assert result["status"] == "unmatched"
    assert result["rejected_matches"][0]["reason"] == "split_small_caps_author_year"
    assert resolver.resolve("K\nTibetan text 1981")["status"] == "exact_online_work_rows"
    assert resolver.resolve("K\nRETSCHMAR another reference 1981")["status"] == "exact_online_work_rows"
    for text in ("AUTHOR 2001, p. 4", "A\nUTHOR 2001, p. 4", "Author 2001"):
        result = resolver.resolve(text)
        assert result["status"] == "exact_online_publication_rows"
        match = result["matches"][0]
        assert text[match["start"]:match["end"]] == match["label"]
        assert match["reference_key"] == "Author 2001"
        assert match["print_status"] == "unverified"
    assert resolver.resolve("Author 20010")["status"] == "unmatched"
    assert resolver.resolve("Unknown 2001")["status"] == "unmatched"


def test_same_dom_disambiguates_without_longest_match_guess():
    rows = parse(WORK.replace("PW", "Dol")) + parse(WORK.replace("PW", "Dol4"))
    resolver = bib.AuthorityResolver(bib.authority_graph(rows)[0], rows)
    evidence = [{"label": "Dol4", "start": 1, "end": 5, "expansion": rows[1]["text"]}]
    result = resolver.resolve_dom("(Dol4 12)", evidence)
    assert result["status"] == "exact_online_work_rows"
    assert result["matches"][0]["label"] == "Dol4"
    assert len(result["spelling_candidates"]) == 2
    evidence[0]["expansion"] = "different edition"
    assert resolver.resolve_dom("(Dol4 12)", evidence)["status"] == "ambiguous"
    evidence[0].update(label="Other", start=0, end=5)
    result = resolver.resolve_dom("Other 12", evidence)
    assert result["status"] == "ambiguous"
    assert result["unresolved_dom_components"][0]["authority_ids"] == []
    with pytest.raises(ValueError, match="span mismatch"):
        resolver.resolve_dom("Other 12", [{**evidence[0], "start": 1}])


def test_reviewed_metadata_fail_closed_and_exports_useful_bibtex(tmp_path):
    rows = parse(PUBLICATION, "publication")
    row = rows[0]
    review = {"occurrence_id": row["occurrence_id"], "source_sha256": row["source_sha256"],
              "label": row["label"], "entry_type": "book",
              "fields_json": json.dumps({"author": "Author, A.", "title": "Title & subtitle", "year": "2001"}),
              "evidence_note": "Reviewed against exact cached table row; print unverified"}
    path = tmp_path / "review.tsv"

    def write(value):
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, delimiter="\t", fieldnames=review.keys())
            writer.writeheader()
            writer.writerow(value)

    write(review)
    bib.apply_metadata_reviews(rows, path)
    exported = bib.export_bibtex(rows)
    assert "@book{" in exported and "  author = {Author, A.}" in exported
    assert "print compatibility unverified" in exported
    for update, message in (({"source_sha256": "stale"}, "stale"),
                            ({"fields_json": '{"title":"Invented"}'}, "title absent"),
                            ({"fields_json": '{"year":"2002"}'}, "year disagrees"),
                            ({"fields_json": '{"unsupported":"x"}'}, "unsupported")):
        write({**review, **update})
        with pytest.raises(ValueError, match=message):
            bib.apply_metadata_reviews(rows, path)


def test_invalid_source_and_abbreviation_scope():
    body = WORK.encode()
    with pytest.raises(ValueError, match="hash/status"):
        bib.parse_page(body, {"sha256": "wrong", "http_status": 200}, "work")
    with pytest.raises(ValueError, match="no recognized"):
        parse("<table><tr><td>Ed.</td><td>Edition</td></tr></table>", "abbreviation")
    assert parse(ABBREVIATION, "abbreviation")[0]["label"] == "Ed."


def test_relation_review_is_occurrence_hash_and_locator_checked(tmp_path):
    rows = parse(WORK.replace("Title</i>.", "Title</i>. Ed.: Author 2001, pp. 1–9.")) + parse(PUBLICATION, "publication")
    _, relations = bib.authority_graph(rows)
    source, publication = rows
    review = dict(occurrence_id=source["occurrence_id"], ordinal=1,
        source_sha256=source["source_sha256"], label=source["label"], reference_key="Author 2001",
        publication_occurrence_id=publication["occurrence_id"], publication_sha256=publication["source_sha256"],
        relation_kind="edition_in_publication", locator="pp. 1–9", source_excerpt="Ed.: Author 2001, pp. 1–9.",
        evidence_note="Explicit edition statement, online only")
    path = tmp_path / "reviews.tsv"
    def write(value):
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=review, delimiter="\t")
            writer.writeheader()
            writer.writerow(value)
    write(review)
    bib.apply_relation_reviews(rows, relations, path)
    assert relations[0]["status"] == "reviewed_online_relation"
    assert relations[0]["print_status"] == "unverified"
    for update, message in (({"source_sha256": "stale"}, "stale"),
                            ({"source_excerpt": "invented"}, "absent"),
                            ({"locator": "pp. 99"}, "locator"),
                            ({"relation_kind": "guess"}, "unsupported")):
        write({**review, **update})
        with pytest.raises(ValueError, match=message):
            bib.apply_relation_reviews(rows, relations, path)


def test_dom_work_does_not_discard_separate_publication_component():
    rows = parse(WORK) + parse(PUBLICATION, "publication")
    authorities, _ = bib.authority_graph(rows)
    result = bib.AuthorityResolver(authorities, rows).resolve_dom("PW12; Author 2001", [
        {"label": "PW", "start": 0, "end": 2, "expansion": rows[0]["text"]}])
    assert result["status"] == "exact_online_source_rows"
    assert [m["label"] for m in result["matches"]] == ["PW", "Author 2001"]


def test_dom_loader_requires_consistent_source_hashes():
    with sqlite3.connect(":memory:") as db:
        db.executescript("""
            CREATE TABLE citation(id,raw_text);
            CREATE TABLE lexical_record(id,record_json);
            CREATE TABLE citation_siglum_badw_authority(citation_id,siglum_ordinal,authority_id,occurrence_source_id,occurrence_ordinal);
            CREATE TABLE citation_siglum(citation_id,ordinal,siglum,visible_start,visible_end,source_id,source_sha256,source_snapshot_id);
            CREATE TABLE badw_siglum_candidate(id,expansion);
            CREATE TABLE badw_siglum_occurrence(candidate_id,source_id,ordinal_in_article,source_sha256);
            CREATE TABLE source_object(snapshot_id,source_id,source_sha256,stable_url);
            INSERT INTO citation VALUES('c','PW 12');
            INSERT INTO citation_siglum_badw_authority VALUES('c',1,'a','source',3);
            INSERT INTO citation_siglum VALUES('c',1,'PW',10,12,'source','sha','snapshot');
            INSERT INTO badw_siglum_candidate VALUES('a','Expansion');
            INSERT INTO badw_siglum_occurrence VALUES('a','source',3,'sha');
            INSERT INTO source_object VALUES('snapshot','source','sha','https://example.test/lemma');
        """)
        db.execute("INSERT INTO lexical_record VALUES(?,?)", ('c', json.dumps({"raw_text": "PW 12",
            "source_spans": [{"start": 10, "source_id": "source", "source_sha256": "sha"}]})))
        result = bib.dom_citation_evidence(db)
        assert result['c'][0]['start'] == 0 and result['c'][0]['end'] == 2
        assert result['c'][0]['article_start'] == 10
        db.execute("UPDATE badw_siglum_occurrence SET source_sha256='stale'")
        with pytest.raises(ValueError, match="source mismatch"):
            bib.dom_citation_evidence(db)


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
    monkeypatch.setattr(bib, "dom_citation_evidence", lambda db: {
        "h": [{"label": "PW", "start": 0, "end": 2, "expansion": "conflicting edition"}]})
    third = tmp_path / "work/third"
    bib.build(tmp_path, third, schema, staging)
    with sqlite3.connect(third / "bibliography.sqlite") as db:
        assert db.execute("SELECT target_status FROM citation_target").fetchall() == [("candidate",)]
        result = json.loads(db.execute("SELECT record_json FROM citation_resolution WHERE citation_id='h'").fetchone()[0])
        assert result["unparsed_spans"][0]["start"] == 0
