"""Offline tests for the provenance-first lexical SQLite builder."""
from __future__ import annotations

import csv
import gzip
from hashlib import sha256
import json
import sqlite3
from pathlib import Path

import pytest

from badw_source_snapshot import create_snapshot
from build_lexical_database import BuildError, build
from inventory_badw_sigla import inventory
from verify_badw_lexical_source import create_verified_lexical_source
from validate_lexical_record_contract import CONTRACT_VERSION
from stitch_badw_pdf_entries import _span
from badw_canonical_pages import stable_json_bytes
from extract_badw_pdf_lexical_candidates import extract as extract_pdf_lexical


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_tsv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _verified_source(tmp_path: Path) -> tuple[Path, str, str]:
    """Make a tiny, complete C8-like cache/snapshot/parsed-article fixture."""
    canonical = tmp_path / "work/canonical"
    for volume in (2, 3, 4):
        _write_tsv(canonical / f"volume_{volume}/canonical_pages.tsv", ("printed_page", "page_id"),
                   [{"printed_page": 1, "page_id": f"v{volume}-1"}])
        _write_tsv(canonical / f"volume_{volume}/canonical_unknown_glyphs.tsv",
                   ("family", "style", "cid", "glyph_signature", "canonical_page_occurrences"),
                   [{"family": "RabtenTibetan", "style": "regular", "cid": "0002",
                     "glyph_signature": "a" * 64, "canonical_page_occurrences": volume}])
    crosswalk = tmp_path / "work/crosswalk.tsv"
    _write_tsv(crosswalk, ("volume", "printed_page"), [{"volume": 2, "printed_page": 1}])
    coverage = tmp_path / "work/coverage"
    _write_tsv(coverage / "canonical_source_manifest.tsv", ("volume",), [])
    _write_tsv(coverage / "missing_from_canonical_snapshot.tsv", ("volume", "printed_page", "snapshot_status"), [])
    (coverage / "summary.json").parent.mkdir(parents=True, exist_ok=True)
    (coverage / "summary.json").write_text("{}\n", encoding="utf-8")
    registry = tmp_path / "data/registry.tsv"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text("identity\nknown\n", encoding="utf-8")

    url = "https://example.invalid/lemma/ka/1"
    body = b"ka source"
    source_sha = sha256(body).hexdigest()
    cache = tmp_path / "work/cache"
    object_path = cache / "objects/sha256" / source_sha[:2] / source_sha
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(body)
    request = cache / "requests/db/article.json"
    request.parent.mkdir(parents=True, exist_ok=True)
    request.write_text(json.dumps({
        "request_key": "article-1", "requested_url": url, "final_url": url,
        "fetched_at_utc": "2026-09-24T00:00:00Z", "http_status": 200,
        "content_classification": "database_article", "delivery_type": "database_article",
        "valid_resource": True, "sha256": source_sha,
        "object_path": f"objects/sha256/{source_sha[:2]}/{source_sha}",
    }, sort_keys=True) + "\n", encoding="utf-8")
    snapshot = tmp_path / "work/source_snapshot"
    create_snapshot("fixture-20260924", "2026-09-24T12:00:00Z", canonical, crosswalk, coverage,
                    registry, cache, snapshot, tmp_path)
    articles = tmp_path / "work/parsed/articles.jsonl"
    articles.parent.mkdir(parents=True, exist_ok=True)
    articles.write_text(json.dumps({
        "source_identifier": "badw:" + url,
        "source_object": {"sha256": source_sha, "final_url": url},
        "article_source_text": "ka source",
        "dom_full_text": "ka sourceKā title",
        "sigla": [{"source_text": "ka", "expanded_display_text": "Kā title",
                   "expanded_source_text": "Kā title",
                   "locator": {"visible_text_start": 0, "visible_text_end": 2, "dom_path": "/div/span"},
                   "expanded_locator": {"dom_text_start": 9, "dom_text_end": 17, "dom_path": "/div/span/span"}}],
    }, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    verified = tmp_path / "work/verified_source.json"
    create_verified_lexical_source(snapshot, articles, verified, tmp_path)
    return verified, "badw:" + url, source_sha


def _records(source_id: str, source_sha: str) -> list[dict[str, object]]:
    span = [{"source_id": source_id, "source_sha256": source_sha,
             "field": "article_source_text", "start": 0, "end": 2}]
    common = {"contract_version": CONTRACT_VERSION, "source_snapshot_id": "fixture-20260924",
              "extraction_run_id": "test", "source_spans": span}
    return [
        common | {"record_type": "entry", "id": "e1", "layer": "badw_editorial",
                  "headword": {"loc": "ka", "tibetan": "ཀ"}, "homonym": "",
                  "stable_url": source_id.removeprefix("badw:"), "witness_ids": [source_id]},
        common | {"record_type": "sense", "id": "s1", "entry_id": "e1", "ordinal": 1,
                  "source_label": "1.", "definition": "erste Bedeutung"},
        common | {"record_type": "citation", "id": "c1", "entry_id": "e1", "raw_text": "Liś 7",
                  "siglum": "Liś", "locator": "7", "authority_status": "unresolved"},
        common | {"record_type": "attestation", "id": "a1", "entry_id": "e1", "sense_id": "s1",
                  "ordinal": 1, "association_status": "explicit", "tibetan": "ཀ་ཁ",
                  "german_translation": "Beleg", "citation_ids": ["c1"]},
        common | {"record_type": "cross_reference", "id": "x1", "entry_id": "e1", "marker": "↑",
                  "target_label": "kha", "target_url": "https://example.invalid/lemma/kha",
                  "resolution_status": "resolved"},
    ]


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    verified, source_id, source_sha = _verified_source(tmp_path)
    source = tmp_path / "work/records.jsonl"
    source.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in _records(source_id, source_sha)),
                      encoding="utf-8")
    records_manifest = tmp_path / "work/records_manifest.json"
    records_manifest.write_text(json.dumps({
        "diagnostic_count": 0,
        "input_sha256": _digest(tmp_path / "work/parsed/articles.jsonl"),
        "records_sha256": _digest(source),
        "snapshot_id": "fixture-20260924",
        "source_object_count": 1,
        "source_objects": [{"source_identifier": source_id, "sha256": source_sha}],
        "verified_lexical_source_sha256": _digest(verified),
    }, sort_keys=True) + "\n", encoding="utf-8")
    sigla = tmp_path / "sigla.tsv"
    sigla.write_text("canon\twork_title\tintro_line_ref\tallowed_variants\tstatus\nLiś\tLi shi\tabbr_lit_3\tlis\tactive\n",
                     encoding="utf-8")
    return source, sigla, records_manifest, verified


def test_builds_provenance_fts_and_non_resolving_siglum_candidates(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    db, manifest = tmp_path / "lexical.sqlite", tmp_path / "manifest.json"
    report = build(source, db, manifest, sigla=sigla, records_manifest=records_manifest,
                   verified_source_manifest=verified, repo_root=tmp_path)
    assert report["record_counts"] == {"attestation": 1, "citation": 1, "cross_reference": 1, "entry": 1, "sense": 1}
    conn = sqlite3.connect(db)
    assert conn.execute("select loc_headword,tibetan_headword from entry").fetchone() == ("ka", "ཀ")
    expected_sha = json.loads(source.read_text(encoding="utf-8").splitlines()[0])["source_spans"][0]["source_sha256"]
    assert conn.execute("select source_sha256,start_offset,end_offset from record_source_span where record_id='e1'").fetchone() == (expected_sha, 0, 2)
    assert conn.execute("select id from sense_fts where sense_fts match 'erste'").fetchone() == ("s1",)
    assert conn.execute("select id from citation_fts where citation_fts match 'Liś'").fetchone() == ("c1",)
    assert conn.execute("select authority_status,bibliographic_source_id from citation").fetchone() == ("unresolved", None)
    assert conn.execute("select match_method from citation_authority_candidate").fetchone() == ("registry_canonical_exact",)
    assert conn.execute("select value from metadata where key='verified_lexical_source_sha256'").fetchone() == (_digest(verified),)
    conn.close()
    assert json.loads(manifest.read_text(encoding="utf-8"))["logical_sha256"] == report["logical_sha256"]


def test_repeat_build_has_identical_logical_content(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    first = build(source, tmp_path / "one.sqlite", tmp_path / "one.json", sigla=sigla,
                  records_manifest=records_manifest, verified_source_manifest=verified, repo_root=tmp_path)
    second = build(source, tmp_path / "two.sqlite", tmp_path / "two.json", sigla=sigla,
                   records_manifest=records_manifest, verified_source_manifest=verified, repo_root=tmp_path)
    assert first["logical_sha256"] == second["logical_sha256"]


def test_invalid_contract_is_rejected_after_provenance_checks(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    bad = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    bad[0]["headword"] = {"loc": "ka"}
    source.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in bad), encoding="utf-8")
    payload = json.loads(records_manifest.read_text(encoding="utf-8"))
    payload["records_sha256"] = _digest(source)
    records_manifest.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(BuildError, match="invalid lexical records"):
        build(source, tmp_path / "bad.sqlite", tmp_path / "bad.json", sigla=sigla,
              records_manifest=records_manifest, verified_source_manifest=verified, repo_root=tmp_path)


def test_unverified_records_manifest_is_rejected(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    payload = json.loads(records_manifest.read_text(encoding="utf-8"))
    payload["verified_lexical_source_sha256"] = "0" * 64
    records_manifest.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(BuildError, match="not bound"):
        build(source, tmp_path / "bad.sqlite", tmp_path / "bad.json", sigla=sigla,
              records_manifest=records_manifest, verified_source_manifest=verified, repo_root=tmp_path)


def _tooltip_inputs(tmp_path: Path) -> tuple[Path, Path]:
    article = json.loads((tmp_path / "work/parsed/articles.jsonl").read_text(encoding="utf-8"))
    candidates, occurrences, _ = inventory([article])
    candidate_file = tmp_path / "work/siglum_candidates.jsonl"
    occurrence_file = tmp_path / "work/siglum_occurrences.jsonl"
    candidate_file.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in candidates), encoding="utf-8")
    occurrence_file.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in occurrences), encoding="utf-8")
    return candidate_file, occurrence_file


def test_badw_tooltip_authority_does_not_resolve_unlocated_citation_or_print_source(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    candidate_file, occurrence_file = _tooltip_inputs(tmp_path)
    db = tmp_path / "with_tooltips.sqlite"
    report = build(source, db, tmp_path / "with_tooltips.json", sigla=sigla,
                   records_manifest=records_manifest, verified_source_manifest=verified,
                   siglum_candidates=candidate_file, siglum_occurrences=occurrence_file,
                   repo_root=tmp_path)
    assert report["badw_siglum_candidate_count"] == 1
    conn = sqlite3.connect(db)
    assert conn.execute("select siglum,expansion from badw_siglum_candidate").fetchone() == ("ka", "Kā title")
    assert conn.execute("select visible_start,visible_end,tooltip_start,tooltip_end from badw_siglum_occurrence").fetchone() == (0, 2, 9, 17)
    assert conn.execute("select id from badw_siglum_fts where badw_siglum_fts match 'title'").fetchone()[0].startswith("badw:siglum:")
    assert conn.execute("select authority_status,bibliographic_source_id from citation").fetchone() == ("unresolved", None)
    assert conn.execute("select count(*) from citation_siglum_candidate").fetchone() == (0,)
    assert conn.execute("select count(*) from badw_bibliographic_authority").fetchone() == (1,)
    assert conn.execute("select count(*) from citation_siglum_badw_authority").fetchone() == (0,)
    conn.close()


def test_tooltip_links_only_to_the_same_located_citation_siglum(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    citation = next(row for row in rows if row["record_type"] == "citation")
    siglum_span = citation["source_spans"][0]
    citation_span = siglum_span | {"end": 9}
    citation["source_spans"] = [citation_span, siglum_span]
    citation["raw_text"] = "ka source"
    citation["siglum"] = "ka"
    citation["sigla"] = [{"text": "ka", "source_span": siglum_span}]
    source.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    manifest_data = json.loads(records_manifest.read_text(encoding="utf-8"))
    manifest_data["records_sha256"] = _digest(source)
    records_manifest.write_text(json.dumps(manifest_data, sort_keys=True) + "\n", encoding="utf-8")
    candidate_file, occurrence_file = _tooltip_inputs(tmp_path)
    db = tmp_path / "located.sqlite"
    build(source, db, tmp_path / "located.json", sigla=sigla,
          records_manifest=records_manifest, verified_source_manifest=verified,
          siglum_candidates=candidate_file, siglum_occurrences=occurrence_file,
          repo_root=tmp_path)
    conn = sqlite3.connect(db)
    assert conn.execute("select siglum,visible_start,visible_end from citation_siglum").fetchone() == ("ka", 0, 2)
    assert conn.execute("select siglum_ordinal,occurrence_ordinal,match_method from citation_siglum_candidate").fetchone() == (1, 1, "badw_tooltip_same_source_span")
    assert conn.execute("select siglum_ordinal,occurrence_ordinal,link_method from citation_siglum_badw_authority").fetchone() == (1, 1, "exact_visible_source_span")
    assert conn.execute("select a.authority_scope,a.source_status,a.print_bibliography_status,c.expansion "
                        "from badw_bibliographic_authority a join badw_siglum_candidate c on c.id=a.id").fetchone() == (
                            "siglum_expansion", "first_party_tooltip", "unverified", "Kā title")
    assert conn.execute("select o.source_url,o.source_sha256,o.visible_start,o.visible_end,o.tooltip_start,o.tooltip_end "
                        "from citation_siglum_badw_authority l join badw_siglum_occurrence o "
                        "on o.candidate_id=l.authority_id and o.source_id=l.occurrence_source_id "
                        "and o.ordinal_in_article=l.occurrence_ordinal").fetchone() == (
                            "https://example.invalid/lemma/ka/1",
                            json.loads(source.read_text(encoding="utf-8").splitlines()[0])["source_spans"][0]["source_sha256"],
                            0, 2, 9, 17)
    assert conn.execute("select authority_status,bibliographic_source_id from citation").fetchone() == ("unresolved", None)
    conn.close()


def test_tampered_badw_tooltip_inventory_is_rejected(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    candidate_file, occurrence_file = _tooltip_inputs(tmp_path)
    candidates = json.loads(candidate_file.read_text(encoding="utf-8"))
    candidates["expansion"] = "invented title"
    candidate_file.write_text(json.dumps(candidates, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(BuildError, match="differs from verified parsed source"):
        build(source, tmp_path / "tampered.sqlite", tmp_path / "tampered.json", sigla=sigla,
              records_manifest=records_manifest, verified_source_manifest=verified,
              siglum_candidates=candidate_file, siglum_occurrences=occurrence_file,
              repo_root=tmp_path)


def _pdf_witness_inputs(tmp_path: Path, source_text: str = "ཀ་ ka — Liś ↑kha") -> tuple[Path, Path]:
    canonical = tmp_path / "work/pdf_canonical"
    output = tmp_path / "work/pdf_articles"
    output.mkdir(parents=True)
    indexes = {}
    for volume in (2, 3, 4):
        folder = canonical / f"volume_{volume}"
        folder.mkdir(parents=True)
        index = folder / "canonical_pages.tsv"
        if volume == 2:
            runs = [{"run_index": 0, "decoded_unicode": source_text, "y": 700.0,
                     "font_id": "f", "glyphs": []}]
            body_hash = sha256(runs[0]["decoded_unicode"].encode()).hexdigest()
            positioned = {"positioned_text_runs": runs, "visible_text": runs[0]["decoded_unicode"]}
            page = {"page_id": "p2-1", "volume": 2, "printed_page": 1,
                    "positioned_page": positioned,
                    "representative_source": {"canonical_url": "https://example.invalid/pdf/ka",
                                              "source_sha256": "a" * 64},
                    "visible_body_sha256": body_hash,
                    "source_faithful_decoded_text": runs[0]["decoded_unicode"],
                    "representative_positioned_sha256": sha256(stable_json_bytes(positioned)).hexdigest()}
            object_path = folder / "pages/p2-1.json.gz"
            object_path.parent.mkdir()
            with gzip.open(object_path, "wt", encoding="utf-8") as handle:
                json.dump(page, handle, ensure_ascii=False)
            _write_tsv(index, ("page_id", "canonical_object", "visible_body_sha256"),
                       [{"page_id": "p2-1", "canonical_object": "pages/p2-1.json.gz",
                         "visible_body_sha256": body_hash}])
        else:
            _write_tsv(index, ("page_id", "canonical_object", "visible_body_sha256"), [])
        indexes[f"volume_{volume}/canonical_pages.tsv"] = _digest(index)
    span = _span(page, "volume_2/pages/p2-1.json.gz", 0, 1, "entry_start")
    article = {"id": "pdf-entry-1", "volume": 2, "start_printed_page": 1,
               "end_printed_page": 1, "loc_headword": "ka", "tibetan_headword": "ཀ་",
               "homonym": "1", "ending_status": "open_after_last_recovered_page",
               "source_spans": [span], "source_faithful_text": span["source_faithful_text"],
               "derived_reading_text": span["derived_reading_text"], "unknown_glyphs": []}
    blob = json.dumps(article, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with gzip.open(output / "pdf_article_witnesses.jsonl.gz", "wb") as handle:
        handle.write(blob)
    fragment = _span(page, "volume_2/pages/p2-1.json.gz", 0, 1, "page_leading_continuation")
    fragment["volume"] = 2
    fragment_blob = json.dumps(fragment, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with gzip.open(output / "unassigned_page_fragments.jsonl.gz", "wb") as handle:
        handle.write(fragment_blob)
    summary = {"contract_version": "badw-pdf-article-witness-v1",
               "article_logical_sha256": sha256(blob).hexdigest(),
               "unassigned_logical_sha256": sha256(fragment_blob).hexdigest(),
               "input_sha256": indexes,
               "counts": {"article_source_spans": 1, "article_unknown_glyph_occurrences": 0,
                          "unassigned_leading_fragments": 1, "volume_2_articles": 1,
                          "volume_3_articles": 0, "volume_4_articles": 0}}
    (output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return output, canonical


def _pdf_candidate_inputs(tmp_path: Path, pdf_root: Path,
                          variant_gloss: bool = False) -> tuple[Path, Path]:
    with gzip.open(pdf_root / "pdf_article_witnesses.jsonl.gz", "rt", encoding="utf-8") as handle:
        witness = json.loads(next(handle))
    span = witness["source_spans"][0]
    source = witness["source_faithful_text"]
    structure = {"contract_version": "badw-pdf-structural-parser-v6",
        "article_id": witness["id"], "volume": witness["volume"],
        "loc_headword": witness["loc_headword"],
        "tibetan_headword": witness["tibetan_headword"], "homonym": witness["homonym"],
        "source_faithful_sha256": sha256(source.encode()).hexdigest(),
        "source_faithful_text": source,
        "source_objects": [{"page_id": span["page_id"],
            "canonical_object": span["canonical_object"],
            "canonical_object_sha256": None,
            "pdf_url": span["representative_pdf_url"],
            "pdf_sha256": span["representative_pdf_sha256"],
            "source_text_sha256": span["source_text_sha256"],
            "run_start": span["run_start"],
            "run_end_exclusive": span["run_end_exclusive"]}],
        "visual_lines": [{"text": source, "page_id": span["page_id"],
            "span_index": 0, "printed_page": 1, "run_start": 0,
            "run_end_exclusive": 1, "unknown_glyphs": [],
            "style_spans": [{"start": 0, "end": len(source),
                             "family": "TGaramond", "style": "regular"}]}],
        "divisions": [{"kind": "unsegmented", "label": "",
                       "start_line_index": 0, "end_line_index_exclusive": 1}],
        "candidates": {"german_quotes": [], "parenthetical_citations": [],
                       "adjacent_quote_citation_pairs": []}}
    if variant_gloss:
        italic_start = source.index("kha chiṅ")
        quote_start = source.index("„")
        structure["visual_lines"][0]["style_spans"] = [
            {"start": 0, "end": italic_start, "family": "TGaramond", "style": "regular"},
            {"start": italic_start, "end": quote_start - 1,
             "family": "TGaramond", "style": "italic"},
            {"start": quote_start - 1, "end": len(source),
             "family": "TGaramond", "style": "regular"}]
        structure["candidates"]["german_quotes"] = [{
            "visual_start": quote_start, "visual_end": len(source),
            "division_index": 0, "start_line_index": 0}]
    lexical = extract_pdf_lexical(structure)
    structure_path = tmp_path / "structure.jsonl.gz"
    lexical_path = tmp_path / "lexical.jsonl.gz"
    with gzip.open(structure_path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(structure, ensure_ascii=False) + "\n")
    with gzip.open(lexical_path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(lexical, ensure_ascii=False) + "\n")
    return structure_path, lexical_path


def test_pdf_witnesses_are_separate_searchable_source_layer(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    pdf_root, canonical = _pdf_witness_inputs(tmp_path)
    report = build(source, tmp_path / "joined.sqlite", tmp_path / "joined.json", sigla=sigla,
                   records_manifest=records_manifest, verified_source_manifest=verified,
                   pdf_article_root=pdf_root, pdf_canonical_root=canonical, repo_root=tmp_path)
    assert report["pdf_article_count"] == 1
    assert report["pdf_source_audit"]["replayed_source_spans"] == 2
    assert report["pdf_unassigned_fragment_count"] == 1
    conn = sqlite3.connect(tmp_path / "joined.sqlite")
    assert conn.execute("select count(*) from source_snapshot").fetchone() == (2,)
    assert conn.execute("select id from pdf_article_fts where pdf_article_fts match 'Liś'").fetchone() == ("pdf-entry-1",)
    assert conn.execute("select source_faithful_text from pdf_article_witness").fetchone() == ("ཀ་ ka — Liś ↑kha",)
    assert conn.execute("select representative_pdf_sha256,run_start,run_end_exclusive from pdf_article_source_span").fetchone() == ("a" * 64, 0, 1)
    assert conn.execute("select source_faithful_text from pdf_unassigned_fragment").fetchone() == ("ཀ་ ka — Liś ↑kha",)
    assert conn.execute("select count(*) from pdf_unassigned_fragment_fts where pdf_unassigned_fragment_fts match 'Liś'").fetchone() == (1,)
    assert conn.execute("select count(*) from entry").fetchone() == (1,)
    conn.close()


def test_pdf_witness_source_tampering_fails_closed(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    pdf_root, canonical = _pdf_witness_inputs(tmp_path)
    object_path = canonical / "volume_2/pages/p2-1.json.gz"
    with gzip.open(object_path, "rt", encoding="utf-8") as handle:
        page = json.load(handle)
    page["positioned_page"]["positioned_text_runs"][0]["decoded_unicode"] = "invented"
    with gzip.open(object_path, "wt", encoding="utf-8") as handle:
        json.dump(page, handle, ensure_ascii=False)
    with pytest.raises(BuildError, match="canonical positioned page hash mismatch"):
        build(source, tmp_path / "rejected.sqlite", tmp_path / "rejected.json", sigla=sigla,
              records_manifest=records_manifest, verified_source_manifest=verified,
              pdf_article_root=pdf_root, pdf_canonical_root=canonical, repo_root=tmp_path)


def test_pdf_candidates_are_staged_without_promotion(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    pdf_root, canonical = _pdf_witness_inputs(tmp_path, "Bedeutung.")
    structure, lexical = _pdf_candidate_inputs(tmp_path, pdf_root)
    report = build(source, tmp_path / "staged.sqlite", tmp_path / "staged.json",
                   sigla=sigla, records_manifest=records_manifest,
                   verified_source_manifest=verified, pdf_article_root=pdf_root,
                   pdf_canonical_root=canonical, pdf_structure=structure,
                   pdf_lexical_candidates=lexical, repo_root=tmp_path)
    assert report["pdf_candidate_counts"] == {"articles": 1, "definition": 1}
    conn = sqlite3.connect(tmp_path / "staged.sqlite")
    assert conn.execute("SELECT kind,text,status FROM pdf_lexical_candidate").fetchall() == [
        ("definition", "Bedeutung.", "unverified_typographic_candidate")]
    assert conn.execute("SELECT count(*) FROM sense WHERE entry_id LIKE 'badw:pdf:%'").fetchone() == (0,)
    assert conn.execute("SELECT count(*) FROM attestation WHERE entry_id LIKE 'badw:pdf:%'").fetchone() == (0,)
    assert conn.execute("SELECT structural_contract_version,lexical_contract_version "
                        "FROM pdf_article_analysis").fetchone() == (
                            "badw-pdf-structural-parser-v6", "badw-pdf-lexical-candidates-v7")
    conn.close()


def test_pdf_variant_gloss_is_staged_without_attestation_promotion(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    pdf_root, canonical = _pdf_witness_inputs(tmp_path, "auch kha chiṅ „eine Variante“")
    structure, lexical = _pdf_candidate_inputs(tmp_path, pdf_root, variant_gloss=True)
    report = build(source, tmp_path / "staged.sqlite", tmp_path / "staged.json",
                   sigla=sigla, records_manifest=records_manifest,
                   verified_source_manifest=verified, pdf_article_root=pdf_root,
                   pdf_canonical_root=canonical, pdf_structure=structure,
                   pdf_lexical_candidates=lexical, repo_root=tmp_path)
    assert report["pdf_candidate_counts"]["variant_gloss"] == 1
    conn = sqlite3.connect(tmp_path / "staged.sqlite")
    assert conn.execute("SELECT kind,status FROM pdf_lexical_candidate").fetchall() == [
        ("variant_gloss", "source_variant_gloss_candidate"),
        ("translation", "source_quote_candidate")]
    assert conn.execute("SELECT count(*) FROM attestation WHERE entry_id LIKE 'badw:pdf:%'").fetchone() == (0,)
    conn.close()


def test_pdf_candidate_tampering_fails_closed(tmp_path: Path):
    source, sigla, records_manifest, verified = _write_inputs(tmp_path)
    pdf_root, canonical = _pdf_witness_inputs(tmp_path, "Bedeutung.")
    structure, lexical = _pdf_candidate_inputs(tmp_path, pdf_root)
    with gzip.open(lexical, "rt", encoding="utf-8") as handle:
        row = json.loads(next(handle))
    row["definitions"][0]["text"] = "invented"
    with gzip.open(lexical, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with pytest.raises(BuildError, match="PDF lexical candidate replay mismatch"):
        build(source, tmp_path / "rejected.sqlite", tmp_path / "rejected.json",
              sigla=sigla, records_manifest=records_manifest,
              verified_source_manifest=verified, pdf_article_root=pdf_root,
              pdf_canonical_root=canonical, pdf_structure=structure,
              pdf_lexical_candidates=lexical, repo_root=tmp_path)
