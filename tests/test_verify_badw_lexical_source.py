"""Tests for the immutable BAdW HTML-to-lexical provenance contract."""
from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path

import pytest
import verify_badw_lexical_source as verifier

from badw_source_snapshot import create_snapshot
from validate_lexical_record_contract import CONTRACT_VERSION
from verify_badw_lexical_source import (
    VerificationError,
    audit_lexical_records,
    create_verified_lexical_source,
    main,
    verify_verified_lexical_source,
)


def _tsv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _fixture(root: Path) -> tuple[Path, Path, str, str]:
    canonical = root / "work/canonical"
    for volume in (2, 3, 4):
        _tsv(canonical / f"volume_{volume}/canonical_pages.tsv", ("printed_page", "page_id"),
             [{"printed_page": 1, "page_id": f"v{volume}-1"}])
        _tsv(canonical / f"volume_{volume}/canonical_unknown_glyphs.tsv",
             ("family", "style", "cid", "glyph_signature", "canonical_page_occurrences"),
             [])
    crosswalk = root / "work/crosswalk.tsv"
    _tsv(crosswalk, ("volume", "printed_page"), [{"volume": 2, "printed_page": 1}])
    coverage = root / "work/coverage"
    _tsv(coverage / "canonical_source_manifest.tsv", ("volume",), [])
    _tsv(coverage / "missing_from_canonical_snapshot.tsv", ("volume", "printed_page", "snapshot_status"), [])
    (coverage / "summary.json").parent.mkdir(parents=True, exist_ok=True)
    (coverage / "summary.json").write_text("{}\n", encoding="utf-8")
    registry = root / "data/registry.tsv"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text("identity\nknown\n", encoding="utf-8")

    url, text = "https://example.invalid/lemma/ka/1", "ka source\u2028with Unicode"
    raw = text.encode("utf-8")
    source_sha = sha256(raw).hexdigest()
    cache = root / "work/cache"
    object_path = cache / "objects/sha256" / source_sha[:2] / source_sha
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(raw)
    request = cache / "requests/db/ka.json"
    request.parent.mkdir(parents=True, exist_ok=True)
    request.write_text(json.dumps({
        "request_key": "ka", "requested_url": url, "final_url": url,
        "fetched_at_utc": "2026-09-24T00:00:00Z", "http_status": 200,
        "content_classification": "database_article", "delivery_type": "database_article",
        "valid_resource": True, "sha256": source_sha,
        "object_path": f"objects/sha256/{source_sha[:2]}/{source_sha}",
    }, sort_keys=True) + "\n", encoding="utf-8")
    snapshot = root / "work/source_snapshot"
    create_snapshot("fixture-20260924", "2026-09-24T12:00:00Z", canonical, crosswalk, coverage,
                    registry, cache, snapshot, root)
    articles = root / "work/parsed/articles.jsonl"
    articles.parent.mkdir(parents=True, exist_ok=True)
    articles.write_text(json.dumps({
        "source_identifier": "badw:" + url,
        "source_object": {"sha256": source_sha, "final_url": url},
        "article_source_text": text,
    }, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    verified = root / "work/verified_source.json"
    create_verified_lexical_source(snapshot, articles, verified, root)
    return verified, articles, "badw:" + url, source_sha


def _record(source_id: str, source_sha: str, end: int = 2) -> dict[str, object]:
    return {
        "contract_version": CONTRACT_VERSION,
        "source_snapshot_id": "fixture-20260924",
        "extraction_run_id": "fixture",
        "record_type": "entry",
        "id": "e1",
        "layer": "badw_editorial",
        "headword": {"loc": "ka", "tibetan": "ཀ"},
        "homonym": "",
        "stable_url": source_id.removeprefix("badw:"),
        "witness_ids": [source_id],
        "source_spans": [{"source_id": source_id, "source_sha256": source_sha,
                          "field": "article_source_text", "start": 0, "end": end}],
    }


def test_verified_source_is_offline_reproducible_and_preserves_unicode(tmp_path: Path):
    verified, articles, source_id, source_sha = _fixture(tmp_path)
    result = verify_verified_lexical_source(verified, tmp_path)
    assert result["verified"] is True
    assert result["parsed_article_count"] == result["database_cache_object_count"] == 1
    assert json.loads(articles.read_text(encoding="utf-8"))["article_source_text"].endswith("\u2028with Unicode")
    assert result["article_source_objects"] == [{
        "source_identifier": source_id, "final_url": source_id.removeprefix("badw:"),
        "source_sha256": source_sha, "object_path": f"objects/sha256/{source_sha[:2]}/{source_sha}",
        "request_key": "ka",
    }]


def test_span_audit_rejects_out_of_range_and_source_hash_mismatch(tmp_path: Path):
    verified, _articles, source_id, source_sha = _fixture(tmp_path)
    records = tmp_path / "work/records.jsonl"
    records.write_text(json.dumps(_record(source_id, source_sha, end=99), ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(VerificationError, match="outside"):
        audit_lexical_records(records, verified, tmp_path)
    records.write_text(json.dumps(_record(source_id, "0" * 64), ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(VerificationError, match="source hash mismatch"):
        audit_lexical_records(records, verified, tmp_path)


def test_verified_source_rejects_parser_inventory_mutation(tmp_path: Path):
    verified, articles, _source_id, _source_sha = _fixture(tmp_path)
    row = json.loads(articles.read_text(encoding="utf-8"))
    row["source_object"]["sha256"] = "0" * 64
    articles.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(VerificationError, match="disagrees"):
        verify_verified_lexical_source(verified, tmp_path)


def test_verify_source_cli_reports_concise_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                    monkeypatch: pytest.MonkeyPatch):
    verified, articles, _source_id, _source_sha = _fixture(tmp_path)
    output = tmp_path / "work/second_verified_source.json"
    snapshot = tmp_path / "work/source_snapshot"
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    assert main(["verify-source", "--snapshot-root", str(snapshot), "--articles", str(articles),
                 "--output", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["parsed_article_count"] == 1
    assert report["output"] == str(output)
    assert report["verified_source_manifest_sha256"] == sha256(output.read_bytes()).hexdigest()
    assert "article_source_objects" not in report
