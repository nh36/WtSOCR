"""Offline tests for the provenance-first lexical SQLite builder."""
from __future__ import annotations

import csv
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


def test_badw_tooltips_are_searchable_candidates_but_not_resolved_authorities(tmp_path: Path):
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
